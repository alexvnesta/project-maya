"""Deployment default only; explicit request effort remains authoritative."""
def install(server, default=100):
    if type(default) is not int or default!=100:raise ValueError('Only qualified maximum default100')
    original=server.Service.effort_default
    def effort_default(service):
        value=original(service)
        return default if value is None or value=='' else value
    server.Service.effort_default=effort_default
