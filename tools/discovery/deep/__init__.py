"""tools.discovery.deep — Phase 2 deep discovery (docs/phases/phase-2-design.md).

    extract.py      2.1 + 2.2  batched element capture: frames, shadow DOM, wider selector set,
                               constraints, container-scoped role locators
    forms.py        2.3        observed validation oracle -> form_model.json
    crawl.py        2.4–2.7    multi-role BFS crawl -> app_map / api_inventory /
                               permission_matrix / baseline
    service.py                 run once per project, reuse, write the artifacts
    config.py                  `discovery:` and `auth.roles:` blocks of project.yaml

Everything is off unless project.yaml sets `discovery.deep: true`.
"""


def ensure_app_discovery(*args, **kwargs):
    from tools.discovery.deep.service import ensure_app_discovery as _run
    return _run(*args, **kwargs)
