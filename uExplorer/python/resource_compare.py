"""Read-only structured resource comparison through the independent core."""
from resource_view import classify

MAX_OBJECTS = 5000
MAX_OBJECT_BYTES = 8 * 1024 * 1024
MAX_DIFFERENCES = 32


def differences(left, right):
    """Ignore relocation addresses, preserving exact words and reference paths."""
    result = [];pending = [('',left,right)]
    while pending and len(result)<MAX_DIFFERENCES:
        path,a,b = pending.pop()
        if type(a) is not type(b):
            result.append(path+': разные типы');continue
        if isinstance(a,dict):
            ignored = {'native_offset','decoded_native_bytes','remaining_offset'}
            reference = all('path' in x and 'class' in x for x in (a,b))
            if reference:ignored.add('id')
            keys = (a.keys()|b.keys())-ignored
            for key in sorted(keys,reverse=True):
                part=path+'/'+key.replace('~','~0').replace('/','~1')
                if key not in a or key not in b:
                    result.append(part+': поле отсутствует в одном объекте')
                    if len(result)>=MAX_DIFFERENCES:break
                else:pending.append((part,a[key],b[key]))
        elif isinstance(a,list):
            if len(a)!=len(b):result.append(path+f': длина {len(a)} → {len(b)}')
            # Iterate without copying huge arrays; bool and int remain distinct.
            for index,(x,y) in enumerate(zip(a,b)):
                if type(x) is type(y) and not isinstance(x,(dict,list)) and x==y:
                    continue
                result.extend(path+'/'+str(index)+suffix for suffix in differences(x,y))
                if len(result)>=MAX_DIFFERENCES:break
        elif a!=b:
            def brief(value):
                text=repr(value)
                return text[:100]+'…' if len(text)>100 else text
            result.append(path+': '+brief(a)+' → '+brief(b))
    return result[:MAX_DIFFERENCES]


def inventory_table(inventory):
    entries=inventory['candidates']
    if len(entries)>MAX_OBJECTS:
        raise ValueError('Comparison exceeds 5000 resource exports per package')
    table={}
    for item in entries:
        key=(item['path'],item['class'])
        if key in table:raise ValueError('Ambiguous resource identity: '+repr(key))
        table[key]=item
    return table


def compare_resources(core, original, candidate, cancelled=lambda:False, progress=lambda *args:None):
    inventories=[core.request(operation='resource_inventory',path=path)['result']
                 for path in (original,candidate)]
    tables=[inventory_table(inv) for inv in inventories]
    keys=sorted(tables[0].keys()|tables[1].keys())
    report=dict(original=original,candidate=candidate,rows=[],cancelled=False,total=len(keys),
                excluded_script_exports=[inv.get('excluded_script_exports',0) for inv in inventories],
                profiles=[(inv.get('version'),inv.get('licensee')) for inv in inventories])
    for index,key in enumerate(keys):
        if cancelled():
            report['cancelled']=True;break
        row=dict(path=key[0],class_name=key[1],status='unverified',details=[])
        a,b=(table.get(key) for table in tables)
        if a is None or b is None:
            row.update(status='different',details=['Объект отсутствует в '+('оригинале' if a is None else 'кандидате')])
        else:
            operation=classify(a)[1]
            if operation is None:
                row['details']=['Независимый reader для этого класса отсутствует']
            elif operation=='blocking_volume':
                row['details']=['Сохранённый снимок BlockingVolume не является полной реконструкцией']
            elif max(a.get('serial_bytes',0),b.get('serial_bytes',0))>MAX_OBJECT_BYTES:
                row['details']=['Объект превышает лимит сравнения 8 МиБ']
            else:
                try:
                    left=core.request(operation=operation,path=original,object_id=a['id'])['result']
                    if cancelled():report['cancelled']=True;break
                    right=core.request(operation=operation,path=candidate,object_id=b['id'])['result']
                    if operation=='model' and any(
                        not isinstance(value,dict) or value.get('status')!='decoded' or
                        value.get('interpretation')=='opaque' or value.get('remaining_bytes')!=0
                        for value in (left,right)
                    ):
                        row['details']=['Непроверенный или частичный разбор Model; '
                                        'совпадение полной структуры не установлено']
                    else:
                        metadata=differences({k:a[k] for k in ('flags','outer')},
                                             {k:b[k] for k in ('flags','outer')})
                        details=metadata+differences(left,right)
                        row.update(status='different' if details else 'equal',details=details[:MAX_DIFFERENCES])
                except (RuntimeError,ValueError) as error:
                    row['details']=[str(error)]
        report['rows'].append(row);progress(index+1,len(keys),key[0])
    report['complete']=not report['cancelled'] and len(report['rows'])==len(keys)
    report['equal']=bool(keys) and report['complete'] and all(r['status']=='equal' for r in report['rows'])
    return report
