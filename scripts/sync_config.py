#!/usr/bin/env python3
"""Bring your own config up to date with the template: take over new entries from
config.example.toml, keep your own values.

    python scripts/sync_config.py            # update ~/.config/slate/config.toml
    python scripts/sync_config.py --dry-run  # only show what would change

Result = text of the template (with all comments), in it:
- every own value that differs from the template, in its place;
- own keys the template does not know, at the end of their section (a commented-out
  example "# key = …" gets replaced by it), own sections at the end;
- your own header (comments at the very top), if there is one.
Own comments in other places are lost.

Safety: before writing, it checks that the result is exactly "template + own values";
otherwise nothing is written. The old file stays as config.toml.bak.

Runs automatically before every commit that changes config.example.toml (scripts/git-hooks).
"""
import argparse
import difflib
import json
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from config import config_path  # noqa: E402

TEMPLATE = REPO / "config.example.toml"
HEADER_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")
ENTRY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*)$")
COMMENTED_RE = re.compile(r"^\s*#\s*([A-Za-z0-9_-]+)\s*=")


def flatten(table, prefix=()):
    """{'ui': {'a': 1}} -> {('ui', 'a'): 1}"""
    out = {}
    for key, value in table.items():
        if isinstance(value, dict):
            out.update(flatten(value, prefix + (key,)))
        else:
            out[prefix + (key,)] = value
    return out


def tables(table, prefix=()):
    """All sections, including empty ones: {('colors',), ('colors', 'light'), …}"""
    out = set()
    for key, value in table.items():
        if isinstance(value, dict):
            out.add(prefix + (key,))
            out |= tables(value, prefix + (key,))
    return out


def toml_value(value):
    """Python value as TOML text (strings, numbers, true/false, lists)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # same escapes as TOML basic strings
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    raise ValueError(f"Cannot write value {value!r}")


def split_comment(rest):
    """'"#fff"   # comment' -> ('"#fff"', '   # comment'); # inside strings does not count."""
    quote, i = None, 0
    while i < len(rest):
        ch = rest[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2  # skip an escape like \"
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            value = rest[:i].rstrip()
            return value, rest[len(value):]
        i += 1
    return rest.rstrip(), ""


def header_block(text):
    """Comment lines at the very top (up to the first empty or non-comment line)."""
    lines = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        lines.append(line)
    return lines


def merge(template_text, user_text):
    """Returns: (new text, newly added keys, own values)."""
    template = tomllib.loads(template_text)
    user = tomllib.loads(user_text)
    t_flat, u_flat = flatten(template), flatten(user)
    changed = {k: v for k, v in u_flat.items() if k in t_flat and t_flat[k] != v}
    extra = {k: v for k, v in u_flat.items() if k not in t_flat}
    added = [k for k in t_flat if k not in u_flat]

    lines = template_text.splitlines()
    # Header: your own, if there is one
    own_header, template_header = header_block(user_text), header_block(template_text)
    if own_header:
        lines = own_header + lines[len(template_header):]

    out, section, pending = [], (), dict(extra)

    def flush_section():
        """Append own keys of this section that have not been placed yet."""
        rest = [(k, v) for k, v in pending.items() if k[:-1] == section]
        if not rest:
            return
        while out and not out[-1].strip():  # insert before the empty lines at the end of the section
            out.pop()
        for k, v in rest:
            out.append(f"{k[-1]} = {toml_value(v)}")
            del pending[k]
        out.append("")

    for line in lines:
        match = HEADER_RE.match(line)
        if match:
            flush_section()
            section = tuple(part.strip().strip('"') for part in match.group(1).split("."))
            out.append(line)
            continue
        match = ENTRY_RE.match(line)
        if match and not line.lstrip().startswith("#"):
            key = section + (match.group(2),)
            if key in changed:
                _, comment = split_comment(match.group(4))
                line = f"{match.group(1)}{match.group(2)}{match.group(3)}{toml_value(changed[key])}{comment}"
            out.append(line)
            continue
        match = COMMENTED_RE.match(line)
        if match and section + (match.group(1),) in pending:  # replace the example with your own value
            key = section + (match.group(1),)
            out.append(f"{match.group(1)} = {toml_value(pending.pop(key))}")
            continue
        out.append(line)
    flush_section()

    # Own sections the template does not know at all
    leftovers = {}
    for key, value in pending.items():
        leftovers.setdefault(key[:-1], []).append((key[-1], value))
    if leftovers:
        out += ["", "# --- Own entries (not in the template) ---"]
        for table, entries in leftovers.items():
            out.append(f"[{'.'.join(table)}]")
            out += [f"{k} = {toml_value(v)}" for k, v in entries]
            out.append("")
    text = "\n".join(out).rstrip() + "\n"

    # Cross-check: result = template + own values
    expected = dict(t_flat)
    expected.update(u_flat)
    result = tomllib.loads(text)
    if flatten(result) != expected or not tables(template) <= tables(result):
        raise ValueError("Merging would give different values; nothing written")
    return text, added, sorted(set(changed) | set(extra))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="only show")
    parser.add_argument("--config", type=Path, default=None, help="instead of ~/.config/slate/config.toml")
    args = parser.parse_args()
    target = args.config or config_path()
    if not target.is_file():
        print(f"[sync_config] {target} does not exist, nothing to do (the tool uses default values)")
        return 0
    old = target.read_text()
    try:
        new, added, own = merge(TEMPLATE.read_text(), old)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        print(f"[sync_config] {e}", file=sys.stderr)
        return 1
    if new == old:
        print(f"[sync_config] {target} is up to date")
        return 0
    names = ", ".join(".".join(k) for k in added) or "none"
    print(f"[sync_config] new from the template: {names}")
    print(f"[sync_config] own values kept: {len(own)}")
    if args.dry_run:
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                   str(target), "new"))
        return 0
    target.with_name(target.name + ".bak").write_text(old)
    with open(target, "w") as f:  # in place, permissions stay
        f.write(new)
    print(f"[sync_config] written, old version: {target.name}.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main())
