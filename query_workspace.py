"""Saved analysis SELECTs and editable daily SQL on the designated MVP database."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import providers

ROOT=Path(__file__).resolve().parent
STORE=ROOT/'work/queries.json'
AGGREGATION=ROOT/'work/aggregation.json'
PIPELINE_STORE=ROOT/'work/pipeline_sql.json'
PIPELINE_FILES=('load_daily.sql','aggregate_daily.sql','transform.sql','validate_daily.sql','report_daily.sql')


def catalog():
    builtins=json.loads((ROOT/'sql/analysis_queries.json').read_text(encoding='utf-8'))
    saved=json.loads(STORE.read_text(encoding='utf-8')) if STORE.exists() else []
    overrides={q['id']:q for q in saved}
    return [dict(overrides.get(q['id'],q),builtin=True,default_sql=q['sql']) for q in builtins]+[q for q in saved if q['id'] not in {b['id'] for b in builtins}]


def validate_sql(sql):
    if not isinstance(sql,str) or not 1 <= len(sql.strip()) <= 12000:
        raise ValueError('SQL은 1~12,000자로 입력하세요.')
    sql=sql.strip().removesuffix(';').strip()
    if (not re.match(r'^(SELECT|WITH)\b',sql,re.I) or ';' in sql or
        any(x in sql for x in ('--','/*','#')) or
        re.search(r'\b(INTO|OUTFILE|DUMPFILE|LOAD_FILE|SLEEP|BENCHMARK|GET_LOCK|RELEASE_LOCK)\b',sql,re.I)):
        raise ValueError('단일 SELECT만 실행할 수 있습니다. 주석·파일 접근·잠금 함수는 지원하지 않습니다.')
    return sql


def save_query(title,sql,query_id=None):
    import uuid
    import pipeline as p
    sql=validate_sql(sql)
    if not isinstance(title,str) or not 1<=len(title.strip())<=80:
        raise ValueError('쿼리 이름은 1~80자로 입력하세요.')
    if query_id and query_id not in {q['id'] for q in catalog()}:
        raise ValueError('저장된 쿼리를 찾을 수 없습니다.')
    queries=json.loads(STORE.read_text(encoding='utf-8')) if STORE.exists() else []
    item={'id':query_id or uuid.uuid4().hex,'title':title.strip(),'sql':sql}
    queries=[q for q in queries if q['id']!=item['id']]+[item]
    STORE.parent.mkdir(exist_ok=True)
    p.atomic_json(STORE,queries)
    return item


def pipeline_contents():
    saved=json.loads(PIPELINE_STORE.read_text(encoding='utf-8')) if PIPELINE_STORE.exists() else {}
    return {name:aggregation_settings()['sql'] if name=='aggregate_daily.sql' else saved.get(name,(ROOT/'sql'/name).read_text(encoding='utf-8')) for name in PIPELINE_FILES}


def pipeline_files():
    return [{'name':name,'sql':sql,'default_sql':(ROOT/'sql'/name).read_text(encoding='utf-8')} for name,sql in pipeline_contents().items()]


def validate_pipeline_sql(name,sql):
    if name not in PIPELINE_FILES:raise ValueError('편집할 파이프라인 SQL을 선택하세요.')
    if not isinstance(sql,str) or not 1<=len(sql.strip())<=12000:raise ValueError('SQL은 1~12,000자로 입력하세요.')
    # ponytail: fixed statement slots; quoted semicolons are unsupported, use a SQL parser if contracts expand.
    clean=re.sub(r'(?m)^\s*--[^\n]*','',sql)
    if name=='aggregate_daily.sql':return [validate_sql(clean)]
    parts=[part.strip() for part in clean.split(';') if part.strip()]
    contracts={'load_daily.sql':(('DELETE','mvp_raw_daily',2),('INSERT','mvp_raw_daily',7)),
               'transform.sql':(('DELETE','mvp_history_daily',2),('INSERT','mvp_history_daily',6)),
               'validate_daily.sql':(('SELECT',None,0),('SELECT',None,2)),
               'report_daily.sql':(('SELECT',None,2),('SELECT',None,2),('SELECT',None,2))}
    if len(parts)!=len(contracts[name]):raise ValueError('파이프라인 SQL의 문장 수와 실행 순서를 유지하세요.')
    for part,(operation,table,count) in zip(parts,contracts[name]):
        if part.count('%s')!=count:raise ValueError('파이프라인 SQL의 %s 매개변수 개수와 순서를 유지하세요.')
        if operation=='SELECT':validate_sql(part)
        elif (not re.match(r'^'+operation+r'\s+'+('FROM' if operation=='DELETE' else 'INTO')+r'\s+`?'+table+r'`?'+(r'\s+WHERE\b' if operation=='DELETE' else r'(?=\s|\()'),part,re.I) or
              any(s in part for s in ('--','/*','#')) or re.search(r'\b(INTO\s+OUTFILE|LOAD_FILE|SLEEP|BENCHMARK|GET_LOCK|RELEASE_LOCK|RETURNING)\b',part,re.I)):
            raise ValueError('적재·이력 SQL은 해당 MVP 테이블의 DELETE·INSERT만 지원합니다.')
    return parts


def save_pipeline_sql(name,sql):
    import pipeline as p
    validate_pipeline_sql(name,sql)
    if name=='aggregate_daily.sql':save_aggregation(validate_pipeline_sql(name,sql)[0])
    else:
        saved=json.loads(PIPELINE_STORE.read_text(encoding='utf-8')) if PIPELINE_STORE.exists() else {}
        saved[name]=sql.strip();PIPELINE_STORE.parent.mkdir(exist_ok=True);p.atomic_json(PIPELINE_STORE,saved)
    return pipeline_files()


def preview_pipeline(conn,name,sql,day):
    import pipeline as p
    validate_pipeline_sql(name,sql)
    contents=pipeline_contents();contents[name]=sql
    days=(day-timedelta(days=7),day)
    p.acquire_lock(conn)
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute('SELECT report_date AS date, channel, device, visits, page_views, orders, revenue_krw FROM mvp_raw_daily WHERE report_date IN (%s,%s)',days)
            rows=[dict(r,date=r['date'].isoformat()) for r in cur.fetchall()]
        p.validate(rows,days)
        history=p.load_transform(conn,rows,days,p.sql_statements('aggregate_daily.sql',contents)[0],contents)
        p.report_data(conn,days,rows,contents)
        return {'validated':True,'columns':['report_date','channel',*p.METRICS],'rows':history,'truncated':False}
    finally:
        conn.rollback()
        with conn.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',(p.lock_name(conn),))


def selected(query_id,conn=None):
    if isinstance(query_id,str) and query_id.startswith('table:'):
        if conn is None:raise ValueError('테이블 조회는 SQL로 저장한 뒤 예약에 사용하세요.')
        return table_query(conn,query_id[6:])
    for q in catalog():
        if q['id']==query_id:return q
    raise ValueError('저장된 쿼리를 찾을 수 없습니다.')


def tables(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,COLUMN_KEY,IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION')
        result={}
        for r in cur.fetchall():result.setdefault(r['TABLE_NAME'],[]).append({'name':r['COLUMN_NAME'],'type':r['COLUMN_TYPE'],'primary':r['COLUMN_KEY']=='PRI','nullable':r['IS_NULLABLE']=='YES'})
    return result


def schema(conn):
    columns=tables(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT TABLE_NAME,TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME')
        items=[{'name':r['TABLE_NAME'],'kind':r['TABLE_TYPE'],'columns':columns.get(r['TABLE_NAME'],[])} for r in cur.fetchall()]
        cur.execute('SELECT CONSTRAINT_NAME,TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION')
        relations={}
        for r in cur.fetchall():
            key=(r['TABLE_NAME'],r['CONSTRAINT_NAME'])
            relation=relations.setdefault(key,{'from':r['TABLE_NAME'],'to':r['REFERENCED_TABLE_NAME'],'kind':'foreign_key','label':r['CONSTRAINT_NAME'],'columns':[]})
            relation['columns'].append({'from':r['COLUMN_NAME'],'to':r['REFERENCED_COLUMN_NAME']})
    edges=list(relations.values())
    if all({'report_date','channel'}<={c['name'] for c in columns.get(name,[])} for name in ('mvp_raw_daily','mvp_history_daily')):
        edges.append({'from':'mvp_raw_daily','to':'mvp_history_daily','kind':'derived','label':'기본 SQL · 일별·채널별 집계','columns':[{'from':c,'to':c} for c in ('report_date','channel')]})
    return {'tables':items,'relationships':edges}


def table_query(conn,name):
    metadata=tables(conn)
    if not isinstance(name,str) or name not in metadata:raise ValueError('연결된 DB의 테이블을 선택하세요.')
    quoted='`'+name.replace('`','``')+'`'
    sql='SELECT * FROM '+quoted
    # ponytail: only report_date is inferred; other date/filter mappings belong in saved SQL.
    dated=any(c['name']=='report_date' and c['type'].startswith(('date','timestamp')) for c in metadata[name])
    if dated:sql+='\nWHERE report_date >= %(start_date)s AND report_date < DATE_ADD(%(end_date)s, INTERVAL 1 DAY)\nORDER BY report_date DESC'
    return {'id':'table:'+name,'title':name+' 테이블 조회','sql':sql}


def preview(conn,name,day):
    q=table_query(conn,name)
    columns=tables(conn)[name]
    sql='SELECT * FROM `'+name.replace('`','``')+'`'
    if any(c['name']=='report_date' for c in columns):sql+=' ORDER BY report_date DESC'
    return dict(execute(conn,sql,parameters(day),20),table=name,default_sql=q['sql'])


def parameters(day,start=None,end=None):
    return {'report_date':day.isoformat(),'comparison_date':(day-timedelta(days=7)).isoformat(),
            'start_date':(start or day).isoformat(),'end_date':(end or day).isoformat()}


def execute(conn,sql,params,limit=200,own_transaction=True):
    sql=validate_sql(sql)
    names=set(re.findall(r'%\(([a-z_]+)\)s',sql))
    if names-set(params):raise ValueError('지원 날짜 변수: report_date, comparison_date, start_date, end_date')
    # Derived SELECT, read-only transaction and server time limit apply to every query path.
    prepared=re.sub(r'%(?!\([a-z_]+\)s|%)','%%',sql) if names else sql
    with conn.cursor() as cur:
        # Pipeline aggregation must stay inside its existing raw/history write transaction.
        if own_transaction:cur.execute('START TRANSACTION READ ONLY')
        try:
            # Materialization preserves the user's ORDER BY when applying the outer row cap.
            cur.execute("SET STATEMENT optimizer_switch='derived_merge=off', max_statement_time=5 FOR SELECT * FROM ("+prepared+') AS workspace_result LIMIT '+str(limit+1),params if names else None)
            rows=cur.fetchall()
            columns=[d[0] for d in cur.description]
        finally:
            if own_transaction:conn.rollback()
    return {'columns':columns,'rows':rows[:limit],'truncated':len(rows)>limit,'sql':sql,'parameters':params}


def aggregation_settings():
    default=validate_sql((ROOT/'sql/aggregate_daily.sql').read_text(encoding='utf-8'))
    sql=validate_sql(json.loads(AGGREGATION.read_text(encoding='utf-8'))['sql']) if AGGREGATION.exists() else default
    return {'sql':sql,'default_sql':default,'custom':sql!=default}


def save_aggregation(sql):
    import pipeline as p
    sql=validate_sql(sql)
    AGGREGATION.parent.mkdir(exist_ok=True)
    p.atomic_json(AGGREGATION,{'sql':sql})
    return aggregation_settings()


def validate_aggregation(result,day,baseline,comparison_day=None):
    import pipeline as p
    fields=('report_date','channel',*p.METRICS)
    if len(result['columns'])!=len(fields) or set(result['columns'])!=set(fields):
        raise ValueError('집계 출력 컬럼은 report_date, channel, visits, page_views, orders, revenue_krw여야 합니다.')
    if result['truncated']:raise ValueError('보고일·7일 전의 채널별 집계만 반환하세요.')
    normalized=[]
    for row in result['rows']:
        item=dict(row)
        try:
            value=item['report_date'];item['report_date']=value.date() if isinstance(value,datetime) else value if isinstance(value,date) else date.fromisoformat(value)
            for key in p.METRICS:
                value=item[key];number=int(value)
                if value!=number or number<0:raise ValueError()
                item[key]=number
        except (ValueError,TypeError,OverflowError):raise ValueError('집계 날짜와 지표 타입을 확인하세요. 지표는 0 이상의 정수여야 합니다.') from None
        normalized.append(item)
    expected={(d,c) for d in (comparison_day or day-timedelta(days=7),day) for c in p.CHANNELS}
    if len(normalized)!=len(expected) or {(r['report_date'],r['channel']) for r in normalized}!=expected:
        raise ValueError('보고일과 7일 전의 각 채널을 한 행씩 집계하세요. 해당 날짜의 데이터가 적재되어 있어야 합니다.')
    totals=p.analyze(normalized,day,comparison_day)
    if any(totals[d][k]!=baseline[d][k] for d in totals for k in p.METRICS):
        raise ValueError('원본과 집계 합계가 다릅니다. 누락·중복·조인 조건을 확인하세요.')
    return normalized


def preview_aggregation(conn,sql,day):
    import pipeline as p
    params=parameters(day)
    base=execute(conn,aggregation_settings()['default_sql'],params,10)
    baseline=p.analyze(base['rows'],day)
    validate_aggregation(base,day,baseline)
    result=execute(conn,sql,params,10)
    validate_aggregation(result,day,baseline)
    return dict(result,validated=True)


def ask(conn,day,question,query_id):
    import pipeline as p
    q=selected(query_id,conn)
    config=providers.llm_config()
    config['prompt']='질문의 조회 기간을 JSON {"start":"YYYY-MM-DD","end":"YYYY-MM-DD"} 하나로만 답하세요. 기본은 기준일 하루, 최근 N일은 기준일 포함 N일입니다. 최대 31일이고 기준일 이후는 허용하지 않습니다.'
    planned=providers.summarize({'reference_date':day.isoformat(),'question':question},[],config)
    if planned['status']!='succeeded':raise ValueError('AI 연결을 확인하세요.')
    try:period=json.loads(planned['text']);start,end,_,_=p.validate_query_plan(dict(period,group='summary',channel='',device=''),day)
    except (ValueError,TypeError):raise ValueError('조회 기간을 해석하지 못했습니다. 기간을 명시하세요.') from None
    result=execute(conn,q['sql'],parameters(day,start,end))
    config['prompt']='한국어로 질문에 답하세요. 제공된 SQL 조회 결과와 실제 조건만 사용하세요. 잘린 결과는 전체 데이터라고 해석하지 마세요. SQL에 적용되지 않은 필터나 기간을 적용했다고 말하지 마세요. 없는 수치나 원인은 만들지 마세요. 계산이 필요하면 SQL 집계를 제안하세요. [관찰된 변화], [확인할 가설], [다음 분석 제안]으로 구분하세요. 질문: '+question
    answer=providers.summarize({'query':q['title'],'parameters':result['parameters'],'truncated':result['truncated']},result['rows'],config)
    if answer['status']!='succeeded':raise ValueError('AI 분석에 실패했습니다. 조회 결과는 SQL 화면에서 확인하세요.')
    return dict(result,answer=answer['text'],query_title=q['title'])


def report(conn,day,query_id,regenerate=False,refresh=False):
    import os,tempfile,uuid
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Font
    import pipeline as p
    q=selected(query_id,conn)
    p.acquire_lock(conn)
    temporary=None
    try:
        if refresh:
            days=(day-timedelta(days=7),day)
            rows=p.extract(days,None)
            conn.begin()
            p.load_transform(conn,rows,days)
            conn.commit()
        result=execute(conn,q['sql'],parameters(day),5000)
        if result['truncated']:raise ValueError('보고서는 최대 5,000행입니다. SQL에서 집계하거나 범위를 줄이세요.')
        if not result['rows']:raise ValueError('조회 결과가 없어 보고서를 생성하지 않았습니다. 날짜와 적재 상태를 확인하세요.')
        folder=Path(os.environ.get('REPORT_DIR',ROOT/'reports'));folder.mkdir(exist_ok=True)
        manifest=folder/f'daily_report_{day}.json'
        config=providers.llm_config();config['prompt']='한국어로 짧은 분석 보고서를 작성하세요. 제공된 조회 결과만 사용하고 없는 수치나 원인은 만들지 마세요. 비교 기간 데이터가 없으면 증가·감소·추세를 주장하거나 가정하지 마세요. 분석 입력은 최대 200행의 표본이며 전체 결과가 아닐 수 있습니다. [관찰된 변화], [확인할 가설], [다음 분석 제안]으로 구분하세요.'
        identity={'query_id':query_id,'source':'저장 SQL: '+q['title'],'sql':q['sql'],'parameters':result['parameters'],'llm':config,
                  'data_sha256':hashlib.sha256(json.dumps(result['rows'],sort_keys=True,default=str).encode()).hexdigest()}
        if manifest.exists() and not regenerate:
            previous=json.loads(manifest.read_text(encoding='utf-8'))
            path=folder/previous['file']
            if previous['identity']==identity and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==previous['file_sha256']:return path
        analysis=providers.summarize({'query':q['title'],'parameters':result['parameters'],'total_rows':len(result['rows']),'analysis_rows':min(200,len(result['rows']))},result['rows'][:200],config)
        wb=Workbook();sheet=wb.active;sheet.title='조회 데이터';sheet.append(result['columns'])
        for row in result['rows']:
            sheet.append([row[c] if isinstance(row[c],(int,float,Decimal,date,datetime)) else str(row[c]) if row[c] is not None else '' for c in result['columns']])
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value,str):cell.data_type='s'  # Never interpret untrusted SQL strings as formulas.
        for cell in sheet[1]:cell.font=Font(bold=True);cell.data_type='s'
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        ai=wb.create_sheet('AI 분석');ai.append([q['title']]);ai.cell(1,1).data_type='s';ai.append([analysis['status']])
        for line in analysis['text'].splitlines():ai.append([line]);ai.cell(ai.max_row,1).data_type='s'
        handle,temporary=tempfile.mkstemp(dir=folder,suffix='.xlsx',prefix='.report-');os.close(handle)
        wb.save(temporary);wb.close()
        version=1;path=folder/f'daily_report_{day}.xlsx'
        while path.exists():version+=1;path=folder/f'daily_report_{day}_v{version}.xlsx'
        os.link(temporary,path)
        p.atomic_json(manifest,{'file':path.name,'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'identity':identity,
            'kind':'sql','query_title':q['title'],'preview':json.loads(json.dumps(dict(columns=result['columns'],rows=result['rows'][:20]),default=str)),
            'report_date':day.isoformat(),'comparison_date':None,'generated_at':datetime.now(p.KST).isoformat(),
            'totals':{},'analysis':analysis})
        return path
    except Exception:
        conn.rollback()
        raise
    finally:
        if temporary:Path(temporary).unlink(missing_ok=True)
        with conn.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',(p.lock_name(conn),))
