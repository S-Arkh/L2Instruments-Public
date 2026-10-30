"""Extract complete target events, including from an interrupted XML export."""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

source = Path(sys.argv[1])
events = []
block = None
with source.open(encoding='utf-8-sig') as stream:
    for line in stream:
        if line.strip() == '<event>':
            block = [line]
        elif block is not None:
            block.append(line)
            if line.strip() == '</event>':
                text = ''.join(block)
                block = None
                if '<Operation>Load Image</Operation>' not in text:
                    continue
                event = ET.fromstring(text)
                path = event.findtext('Path', '')
                if not path.lower().endswith(('\\clmods.dll', '\\scryderadio.dll')):
                    continue
                events.append({
                    'process': event.findtext('Process_Name'),
                    'pid': event.findtext('PID'),
                    'time': event.findtext('Time_of_Day'),
                    'path': path,
                    'frames': [{c.tag: c.text for c in f} for f in event.findall('stack/frame')],
                })
                if len({e['path'].lower().rsplit('\\', 1)[-1] for e in events}) == 2:
                    break
out = source.with_name('extension-load-stacks.json')
out.write_text(json.dumps({'source': source.name, 'export_interrupted': True,
                           'events': events}, ensure_ascii=False, indent=2), encoding='utf-8')
for e in events:
    print(e['process'], e['path'])
    for f in e['frames']:
        print(' ', f.get('location', f.get('address')))
print('Saved', out)
