# MTA self mutation testing (2026-10-15)

72/100 mutants killed (**72.0%**), 0 not run (cap 25 per target, time box 30.0 min, 880 s). Sources restored: yes (git diff empty).

| Target | File | Mutants | Killed | Survived | Score |
|---|---|---|---|---|---|
| bva | `tools/test_design/bva.py` | 25 | 19 | 6 | 76.0% |
| ep | `tools/test_design/ep.py` | 25 | 13 | 12 | 52.0% |
| triage | `tools/triage/triage.py` | 25 | 21 | 4 | 84.0% |
| linter | `tools/test_creation/assertion_linter.py` | 25 | 19 | 6 | 76.0% |

## Survivors (faults the unit tests let through)

- bva `tools/test_design/bva.py:52` in `numeric_points`: 0 -> 1
- bva `tools/test_design/bva.py:81` in `date_points`: 2 -> 3
- bva `tools/test_design/bva.py:95` in `_step_for`: negate condition
- bva `tools/test_design/bva.py:103` in `fmt_number`: Lt -> LtE
- bva `tools/test_design/bva.py:199` in `generate`: Eq -> NotEq
- bva `tools/test_design/bva.py:200` in `generate`: 0 -> 1
- ep `tools/test_design/ep.py:61` in `invalid_classes`: Eq -> NotEq
- ep `tools/test_design/ep.py:35` in `invalid_classes`: Eq -> NotEq
- ep `tools/test_design/ep.py:65` in `invalid_classes`: IsNot -> Is
- ep `tools/test_design/ep.py:40` in `invalid_classes`: GtE -> Gt
- ep `tools/test_design/ep.py:44` in `invalid_classes`: 1 -> 2
- ep `tools/test_design/ep.py:80` in `_not_matching`: drop `not`
- ep `tools/test_design/ep.py:96` in `valid_classes`: negate condition
- ep `tools/test_design/ep.py:96` in `valid_classes`: Eq -> NotEq
- ep `tools/test_design/ep.py:95` in `valid_classes`: Or -> And
- ep `tools/test_design/ep.py:104` in `_level`: negate condition
- ep `tools/test_design/ep.py:122` in `valid_known`: Is -> IsNot
- ep `tools/test_design/ep.py:131` in `generate`: And -> Or
- triage `tools/triage/triage.py:66` in `_spec_key`: GtE -> Gt
- triage `tools/triage/triage.py:171` in `classify`: Or -> And
- triage `tools/triage/triage.py:184` in `classify`: 3 -> 4
- triage `tools/triage/triage.py:261` in `_history_note`: negate condition
- linter `tools/test_creation/assertion_linter.py:92` in `_is_submit`: And -> Or
- linter `tools/test_creation/assertion_linter.py:123` in `lint_test`: 40 -> 41
- linter `tools/test_creation/assertion_linter.py:161` in `lint_test`: 0 -> 1
- linter `tools/test_creation/assertion_linter.py:132` in `lint_test`: 35 -> 36
- linter `tools/test_creation/assertion_linter.py:151` in `lint_test`: 35 -> 36
- linter `tools/test_creation/assertion_linter.py:111` in `lint_test`: Or -> And
