from my_agent_next.workflow_sdk import Workflow

def build_workflow():
    flow = Workflow()
    flow.mcp('mcp_time', server='l6_time', tool='get_current_time', arguments={}, output='time_result')
    flow.agent('answer', agent='analysis', message='The verified L6 MCP time node output is: {time_result}. Tell the user the current time directly.', output='answer')
    flow.edge('START', 'mcp_time')
    flow.edge('mcp_time', 'answer')
    flow.edge('answer', 'END')
    return flow.compile()
