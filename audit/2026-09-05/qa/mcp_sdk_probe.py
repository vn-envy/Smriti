import asyncio,json,tempfile, pathlib
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    with tempfile.TemporaryDirectory(prefix='smriti-agent-probe-') as tmp:
        params=StdioServerParameters(command='/private/tmp/smriti-qa-20260905/bin/smriti-mcp',args=['--db',str(pathlib.Path(tmp)/'memory.db')])
        log=[]
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                init=await session.initialize();log.append({'initialize':init.model_dump(mode='json')})
                ts=await session.list_tools();log.append({'tools':[t.name for t in ts.tools]})
                cases=[('remember',{'messages':[{'role':'user','content':'Agent audit: project Cedar uses SQLite.'}],'session_id':'audit','timestamp':'2026-09-01T10:00:00Z'}),('remember',{'messages':[{'role':'user','content':'Agent audit: project Cedar uses SQLite.'}],'session_id':'audit','timestamp':'2026-09-01T10:00:00Z'}),('add_fact',{'statement':'Cedar owner is Alice','subject':'Cedar','predicate':'owner','object':'Alice','entities':['Cedar','Alice']}),('add_fact',{'statement':'Cedar owner is Bob','subject':'Cedar','predicate':'owner','object':'Bob','entities':['Cedar','Bob']}),('search',{'query':'Cedar owner','profile':'facts'}),('recall',{'query':'Cedar owner','profile':'facts'}),('facts_about',{'entity':'Cedar'}),('stats',{})]
                for name,args in cases:
                    out=await session.call_tool(name,args);log.append({'tool':name,'result':out.model_dump(mode='json')})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize();out=await session.call_tool('stats',{});log.append({'restart_stats':out.model_dump(mode='json')})
        print(json.dumps(log,indent=2))
asyncio.run(main())
