"""Loaded SysString documents, independent of the XDAT schema and UI language."""
from pathlib import Path
import uuid
from PySide6.QtCore import QObject, Signal
from _interface_core import SysStrings


class StringCatalog(QObject):
    changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.entries = []
        self.active_id = None
        self.generation = 0
        self._snapshot = None

    @property
    def active(self):
        return next((e for e in self.entries if e['id'] == self.active_id), None)

    @property
    def dirty(self):
        return any(e['info']['dirty'] for e in self.entries)

    def snapshot(self):
        return self._snapshot

    @staticmethod
    def load_file(filename, schema='id-ascf-v1', encoding='cp1252', profile='auto'):
        table = SysStrings()
        table.load(str(filename), schema, encoding, profile)
        return table

    def attach(self, table, language):
        filename = table.summary()['file']
        key = str(Path(filename).resolve()).casefold()
        entry = next((e for e in self.entries if str(Path(e['info']['file']).resolve()).casefold() == key), None)
        if entry and entry['info']['dirty']:
            raise ValueError('This SysString has unsaved changes; save it before reopening')
        if entry is None:
            entry = dict(id=uuid.uuid4().hex)
            self.entries.append(entry)
        entry.update(table=table, language=language, info=table.summary(), rows=table.rows())
        self.active_id = entry['id']
        self.notify()
        return entry

    def notify(self):
        self.generation += 1
        entry = self.active
        self._snapshot = {row['id']: row['text'] for row in entry['rows']} if entry else None
        records = [dict(file=e['info']['file'], language=e['language'], schema=e['info']['schema'],
                        encoding=e['info']['encoding'], profile=e['info']['profile']) for e in self.entries]
        import json
        self.settings.setValue('sysstrings/files', json.dumps(records, ensure_ascii=False))
        self.settings.setValue('sysstrings/active_file', entry['info']['file'] if entry else '')
        self.changed.emit()

    def refresh(self, entry):
        entry['info'] = entry['table'].summary()
        entry['rows'] = entry['table'].rows()
        self.notify()

    def activate(self, identifier):
        if identifier != self.active_id:
            if not any(e['id'] == identifier for e in self.entries):
                raise ValueError('Unknown language table')
            self.active_id = identifier
            self.notify()

    def suggest_id(self):
        used = {row['id'] for e in self.entries for row in e['rows']}
        maximum = max((i for i in used if i < 2147483647), default=0)
        candidate = maximum + 1 if maximum < 2147483646 else 1
        while candidate in used and candidate < 2147483647:
            candidate += 1
        if candidate == 2147483647:
            raise ValueError('No available UI string ID')
        return candidate

    def edit(self, entry, identifier, value):
        entry['table'].set(identifier, value)
        self.refresh(entry)

    def change_translations(self, identifier, values, new=False):
        if not 0 <= identifier <= 2147483647:
            raise ValueError('UI string ID must be in 0..2147483647')
        if new and any(e['table'].lookup(identifier) is not None for e in self.entries):
            raise ValueError('ID already exists in a loaded language; use the translation action')
        operations = []
        for entry in self.entries:
            if entry['id'] not in values:
                continue
            value = values[entry['id']]
            if '\0' in value or len(value.encode('utf-8')) > 1024 * 1024:
                raise ValueError('Invalid text')
            before = entry['table'].lookup(identifier)
            if before != value:
                operations.append((entry, before, value))
        applied = []
        try:
            for entry, before, value in operations:
                if before is None:
                    entry['table'].add(identifier, value)
                else:
                    entry['table'].set(identifier, value)
                applied.append(entry)
        except Exception:
            for entry in reversed(applied):
                entry['table'].undo()
            raise
        for entry in applied:
            entry['info'] = entry['table'].summary()
            entry['rows'] = entry['table'].rows()
        self.notify()
