class AgentExecutionError(Exception):
    def __init__(self, step_name: str, message: str):
        super().__init__(message)
        self.step_name = step_name
        self.message = message


class WorkflowExecutionError(Exception):
    def __init__(self, workflow_id: str, message: str):
        super().__init__(message)
        self.workflow_id = workflow_id
        self.message = message
