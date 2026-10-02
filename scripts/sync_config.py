#!/usr/bin/env python3
"""Eigene Config auf den Stand der Vorlage bringen: neue Einträge aus config.example.toml
übernehmen, eigene Werte behalten.

    python scripts/sync_config.py            # ~/.config/slate/config.toml aktualisieren
    python scripts/sync_config.py --dry-run  # nur zeigen, was sich ändern würde

Ergebnis = Text der Vorlage (mit allen Kommentaren), darin:
- jeder eigene Wert, der von der Vorlage abweicht, an seiner Stelle;
- eigene Schlüssel, die die Vorlage nicht kennt, am Ende ihres Abschnitts (ein
  auskommentiertes Beispiel "# key = …" wird dabei ersetzt), eigene Abschnitte am Ende;
- die eigene Kopfzeile (Kommentare ganz oben), falls vorhanden.
Eigene Kommentare an anderen Stellen gehen verloren.

Sicherheit: Vor dem Schreiben wird geprüft, dass das Ergebnis genau "Vorlage + eigene
Werte" ergibt; sonst wird nichts geschrieben. Die alte Datei bleibt als config.toml.bak.

Läuft automatisch vor jedem Commit, der config.example.toml ändert (scripts/git-hooks).
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
    """Alle Abschnitte, auch leere: {('colors',), ('colors', 'light'), …}"""
    out = set()
    for key, value in table.items():
        if isinstance(value, dict):
            out.add(prefix + (key,))
            out |= tables(value, prefix + (key,))
    return out


def toml_value(value):
    """Python-Wert als TOML-Text (Zeichenketten, Zahlen, true/false, Listen)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # gleiche Escapes wie TOML-Basisstrings
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    raise ValueError(f"Wert {value!r} kann nicht geschrieben werden")


def split_comment(rest):
    """'"#fff"   # Kommentar' -> ('"#fff"', '   # Kommentar'); # in Zeichenketten zählt nicht."""
    quote, i = None, 0
    while i < len(rest):
        ch = rest[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2  # Escape wie \" überspringen
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
    """Kommentarzeilen ganz oben (bis zur ersten Leer- oder Nicht-Kommentarzeile)."""
    lines = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        lines.append(line)
    return lines


def merge(template_text, user_text):
    """Rückgabe: (neuer Text, neu übernommene Schlüssel, eigene Werte)."""
    template = tomllib.loads(template_text)
    user = tomllib.loads(user_text)
    t_flat, u_flat = flatten(template), flatten(user)
    changed = {k: v for k, v in u_flat.items() if k in t_flat and t_flat[k] != v}
    extra = {k: v for k, v in u_flat.items() if k not in t_flat}
    added = [k for k in t_flat if k not in u_flat]

    lines = template_text.splitlines()
    # Kopfzeile: die eigene, falls vorhanden
    own_header, template_header = header_block(user_text), header_block(template_text)
    if own_header:
        lines = own_header + lines[len(template_header):]

    out, section, pending = [], (), dict(extra)

    def flush_section():
        """Eigene Schlüssel dieses Abschnitts, die noch nicht untergebracht sind, anhängen."""
        rest = [(k, v) for k, v in pending.items() if k[:-1] == section]
        if not rest:
            return
        while out and not out[-1].strip():  # vor den Leerzeilen am Abschnittsende einfügen
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
        if match and section + (match.group(1),) in pending:  # Beispiel durch eigenen Wert ersetzen
            key = section + (match.group(1),)
            out.append(f"{match.group(1)} = {toml_value(pending.pop(key))}")
            continue
        out.append(line)
    flush_section()

    # Eigene Abschnitte, die die Vorlage gar nicht kennt
    leftovers = {}
    for key, value in pending.items():
        leftovers.setdefault(key[:-1], []).append((key[-1], value))
    if leftovers:
        out += ["", "# --- Eigene Einträge (nicht in der Vorlage) ---"]
        for table, entries in leftovers.items():
            out.append(f"[{'.'.join(table)}]")
            out += [f"{k} = {toml_value(v)}" for k, v in entries]
            out.append("")
    text = "\n".join(out).rstrip() + "\n"

    # Gegenprobe: Ergebnis = Vorlage + eigene Werte
    expected = dict(t_flat)
    expected.update(u_flat)
    result = tomllib.loads(text)
    if flatten(result) != expected or not tables(template) <= tables(result):
        raise ValueError("Zusammenführen ergäbe andere Werte; nichts geschrieben")
    return text, added, sorted(set(changed) | set(extra))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="nur anzeigen")
    parser.add_argument("--config", type=Path, default=None, help="statt ~/.config/slate/config.toml")
    args = parser.parse_args()
    target = args.config or config_path()
    if not target.is_file():
        print(f"[sync_config] {target} gibt es nicht, nichts zu tun (Tool nimmt Standardwerte)")
        return 0
    old = target.read_text()
    try:
        new, added, own = merge(TEMPLATE.read_text(), old)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        print(f"[sync_config] {e}", file=sys.stderr)
        return 1
    if new == old:
        print(f"[sync_config] {target} ist aktuell")
        return 0
    names = ", ".join(".".join(k) for k in added) or "keine"
    print(f"[sync_config] neu aus der Vorlage: {names}")
    print(f"[sync_config] eigene Werte behalten: {len(own)}")
    if args.dry_run:
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                   str(target), "neu"))
        return 0
    target.with_name(target.name + ".bak").write_text(old)
    with open(target, "w") as f:  # in place, Rechte bleiben
        f.write(new)
    print(f"[sync_config] geschrieben, alte Fassung: {target.name}.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main())
