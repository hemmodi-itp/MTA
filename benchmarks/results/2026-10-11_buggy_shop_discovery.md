# Deep discovery metrics — buggy_shop (2026-10-11)

| Metric | Result |
|---|---|
| Element recall (link-reachable) | 100.0% |
| Element recall (all labelled) | 92.3% |
| Constraint capture | 41/41 = 100.0% |
| Page coverage (link-reachable templates × role) | 13/13 = 100.0% |
| Observed validation messages matching the app | 18/18 = 100.0% |
| Deep discovery run | 39.1 s, 23 states, 10 forms, 29 probes, 14 endpoints |

## Scan time (element collection, median of 3)

| Module | Classic s | Deep s | Classic elements | Deep elements | Deep ≤ classic |
|---|---|---|---|---|---|
| M01 | 0.554 | 0.029 | 7 | 7 | yes |
| M02 | 0.917 | 0.039 | 17 | 17 | yes |
| M03 | 0.864 | 0.025 | 12 | 12 | yes |
| M04 | 2.17 | 0.042 | 15 | 15 | yes |
| M05 | 0.793 | 0.02 | 9 | 9 | yes |
| M06 | 0.615 | 0.018 | 8 | 8 | yes |

## Missing elements

- `{"template": "/cart", "role": "user", "testid": "cart-line-quantity", "reachability": "requires_state", "expected": 1, "found": 0}`
- `{"template": "/cart", "role": "user", "testid": "update-quantity", "reachability": "requires_state", "expected": 1, "found": 0}`
- `{"template": "/cart", "role": "user", "testid": "remove-line", "reachability": "requires_state", "expected": 1, "found": 0}`
- `{"template": "/checkout", "role": "user", "testid": "continue-shopping", "reachability": "requires_state", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "brand-link", "reachability": "deep_link", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "nav-products", "reachability": "deep_link", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "nav-new-product", "reachability": "deep_link", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "nav-cart", "reachability": "deep_link", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "nav-upload", "reachability": "deep_link", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "logout-link", "reachability": "deep_link", "expected": 1, "found": 0}`
- `{"template": "/orders/{id}", "role": "user", "testid": "footer-help-link", "reachability": "deep_link", "expected": 1, "found": 0}`
