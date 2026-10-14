"""Phase 8: white-box rule extraction (if guards, pydantic, marshmallow, zod, yup, joi, class-validator), path
templating, routes, contract checks, and the API test generator."""
import json
from pathlib import Path

import pytest

from tools.whitebox import js_rules, python_rules
from tools.whitebox.extract import contract, extract_source


def rules_of(src, lang="py"):
    out = (python_rules.extract_file("x.py", src, "x.py") if lang == "py" else js_rules.extract_file("x.ts", src, "x.ts"))
    return {(r["field"], r["kind"]): r for r in out["rules"]}, out


@pytest.mark.parametrize("path,tmpl", [
    ("/products/{pid}", "/products/{id}"), ("/products/<int:pid>", "/products/{id}"), ("/products/:pid", "/products/{id}"),
    ("/a/{x}/b/{y}/", "/a/{id}/b/{id}"), ("/", "/"), ("/users/<name>/posts", "/users/{id}/posts"),
])
def test_path_templating(path, tmpl):
    assert python_rules.template_path(path) == tmpl


IF_GUARDS = '''
import re
from fastapi import FastAPI, Form, Request
NAME_MAX = 50
LO, HI = 1, 99
CODE_RE = re.compile(r"^[A-Z]{3}$")
KINDS = ("a", "b")
app = FastAPI()

def validate(data):
    errors = []
    name = str(data.get("name") or "").strip()
    if not name:
        if not is_on("FLAG_X"):
            errors.append("Name is required")
    elif (len(name) >= NAME_MAX) if is_on("FLAG_Y") else (len(name) > NAME_MAX):
        errors.append("Name too long")
    raw = data.get("price")
    price_s = "" if raw is None else str(raw).strip()
    if not CODE_RE.match(data.get("code", "")):
        errors.append("bad code")
    if data.get("kind") not in KINDS:
        errors.append("bad kind")
    price = float(price_s)
    if price < 0 and not is_on("FLAG_Z"):
        errors.append("negative")
    return errors

def parse_qty(raw):
    qty = int(str(raw).strip())
    if qty > HI:
        return None
    if qty < LO:
        return None
    return qty

@app.post("/items")
def create(request: Request, name: str = Form(""), qty: str = Form("1")):
    user = api_auth(request)
    errors = validate({"name": name})
    if errors:
        return JSONResponse({"errors": errors}, status_code=422)
    q = parse_qty(qty)
    item = store.get(name)
    if item is None:
        return JSONResponse({"detail": "nf"}, status_code=404)
    return {"id": 1, "name": name}

@app.get("/admin/{uid}")
def admin(request: Request, uid: int):
    if user["role"] != "admin":
        return denied()
    return {}
'''


def test_if_guards_with_flags_constants_and_helpers():
    rules, out = rules_of(IF_GUARDS)
    assert rules[("name", "required")]["guards"] == ["not is_on('FLAG_X')"]
    assert rules[("name", "required")]["message"] == "Name is required"
    assert rules[("name", "length")]["value"] == {"max": 50} and "when not" in rules[("name", "length")]["guards"][0]
    assert rules[("code", "pattern")]["value"] == {"value": "^[A-Z]{3}$"}
    assert rules[("kind", "options")]["value"] == {"values": ["a", "b"]}
    assert rules[("price", "range")]["value"] == {"min": 0}
    assert rules[("qty", "range")]["value"]["integer"] is True
    assert {r["value"].get("max") or r["value"].get("min") for r in out["rules"] if r["field"] == "qty"} == {1, 99}
    assert ("name", "required") in rules and rules[("name", "required")]["citation"].startswith("x.py:")
    assert not any(r["field"] == "name" and r["function"] == "create" and r["kind"] == "required" for r in out["rules"])
    route = {(r["method"], r["path"]): r for r in out["routes"]}
    c = route[("POST", "/items")]
    assert c["auth"] == "api_401" and c["error_status"] == 422 and "validate" in c["validators"]
    assert c["params"]["form"] == ["name", "qty"] and c["response_keys"] == ["id", "name"]
    assert route[("GET", "/admin/{uid}")]["roles"] == ["admin"] and route[("GET", "/admin/{uid}")]["params"]["path"] == ["uid"]
    assert "FLAG_X" in out["flags"]


def test_pydantic_and_marshmallow():
    src = '''
from pydantic import BaseModel, Field, constr, conint
from marshmallow import Schema, fields, validate
class Product(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    price: float = Field(ge=0, le=1000)
    code: constr(pattern=r"^[A-Z]+$")
    qty: conint(gt=0, lt=100) = 1
    note: Optional[str] = None
    kind: Literal["a", "b"]
class ProductSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(max=50))
    qty = fields.Int(validate=[validate.Range(min=1, max=99)])
    kind = fields.Str(validate=validate.OneOf(["a", "b"]))
    code = fields.Str(validate=validate.Regexp(r"^[0-9]+$"))
'''
    _, out = rules_of(src)
    by = {}
    for r in out["rules"]:
        by.setdefault((r["function"], r["field"], r["kind"]), r["value"])
    assert by[("Product", "name", "length")] == {"min": 1, "max": 50}
    assert by[("Product", "price", "range")] == {"min": 0, "max": 1000}
    assert by[("Product", "code", "pattern")] == {"value": "^[A-Z]+$"}
    assert by[("Product", "qty", "range")] == {"min": 1, "max": 99}
    assert ("Product", "name", "required") in by and ("Product", "note", "required") not in by
    assert ("Product", "qty", "required") not in by and by[("Product", "kind", "options")] == {"values": ["a", "b"]}
    assert by[("ProductSchema", "name", "length")] == {"max": 50} and ("ProductSchema", "name", "required") in by
    assert by[("ProductSchema", "qty", "range")] == {"min": 1, "max": 99}
    assert by[("ProductSchema", "kind", "options")] == {"values": ["a", "b"]}
    assert by[("ProductSchema", "code", "pattern")] == {"value": "^[0-9]+$"}


@pytest.mark.parametrize("src,expect", [
    ("const S = z.object({ name: z.string().min(1).max(50), age: z.number().int().min(0).max(120), "
     "kind: z.enum(['a', 'b']), nick: z.string().optional(), code: z.string().regex(/^[A-Z]+$/) });",
     {("name", "length"): {"min": 1, "max": 50}, ("age", "range"): {"min": 0, "max": 120, "integer": True},
      ("kind", "options"): {"values": ["a", "b"]}, ("code", "pattern"): {"value": "^[A-Z]+$"},
      ("name", "required"): {"value": True}}),
    ("const s = yup.object({ name: yup.string().required().max(50), qty: yup.number().min(1).max(99), "
     "kind: yup.string().oneOf(['a', 'b']) });",
     {("name", "required"): {"value": True}, ("name", "length"): {"max": 50}, ("qty", "range"): {"min": 1, "max": 99},
      ("kind", "options"): {"values": ["a", "b"]}}),
    ("const s = Joi.object({ name: Joi.string().min(1).max(50).required(), code: Joi.string().pattern(/^x+$/), "
     "kind: Joi.string().valid('a', 'b') });",
     {("name", "length"): {"min": 1, "max": 50}, ("name", "required"): {"value": True},
      ("code", "pattern"): {"value": "^x+$"}, ("kind", "options"): {"values": ["a", "b"]}}),
    ("import { IsNotEmpty, MaxLength, Min, Max, IsIn, Matches } from 'class-validator';\nexport class Dto {\n"
     "  @IsNotEmpty()\n  @MaxLength(50)\n  name: string;\n\n  @Min(1)\n  @Max(99)\n  qty: number;\n\n"
     "  @IsIn(['a', 'b'])\n  kind: string;\n\n  @Matches(/^[0-9]+$/)\n  code: string;\n}\n",
     {("name", "required"): {"value": True}, ("name", "length"): {"max": 50}, ("qty", "range"): {"min": 1, "max": 99},
      ("kind", "options"): {"values": ["a", "b"]}, ("code", "pattern"): {"value": "^[0-9]+$"}}),
], ids=["zod", "yup", "joi", "class-validator"])
def test_js_schema_libraries(src, expect):
    rules, _ = rules_of(src, "js")
    for key, value in expect.items():
        assert rules[key]["value"] == value, (key, rules.get(key))
        assert rules[key]["citation"].startswith("x.ts:")
    if "optional" in src:
        assert ("nick", "required") not in rules


def test_express_routes():
    _, out = rules_of("app.get('/users/:id', h);\nrouter.post(\"/users\", c);", "js")
    assert [(r["method"], r["path_template"]) for r in out["routes"]] == [("GET", "/users/{id}"), ("POST", "/users")]


def test_buggy_shop_extraction_and_contract():
    code = extract_source("benchmarks/apps/buggy_shop", rel_to=".")
    by = {(r["field"], r["kind"], json.dumps(r["value"], sort_keys=True)) for r in code["rules"]}
    for want in [("name", "required"), ("name", "length"), ("price", "range"), ("category", "options"),
                 ("quantity", "range"), ("price", "pattern"), ("description", "length")]:
        assert any(b[:2] == want for b in by), want
    routes = {(r["method"], r["path_template"]): r for r in code["routes"]}
    assert routes[("POST", "/api/products")]["error_status"] == 422
    assert routes[("GET", "/admin")]["roles"] == ["admin"] and "quantity" in routes[("POST", "/cart/add")]["stateful_fields"]
    assert routes[("GET", "/api/orders/{id}")]["access_checks"] == ["_can_see_order"]
    fm = {"forms": [{"method": "post", "action": "/products", "dom_id": "f", "url_template": "/products/new",
                     "fields": [{"name": "name", "constraints": {"required": True}},
                                {"name": "nickname", "constraints": {}}]},
                    {"method": "post", "action": "/nowhere", "fields": []},
                    {"method": "post", "action": "/products/7/delete", "fields": []}]}
    found = {(c["type"], c.get("field")) for c in contract(code, fm, None)}
    assert ("field_ignored", "nickname") in found and ("no_route", None) in found
    assert not any(c["type"] == "server_weaker" and c.get("field") == "name" for c in contract(code, fm, None))
    assert sum(1 for t, _ in found if t == "no_route") == 1          # /products/7/delete is templated to a real route


def test_api_generator_for_buggy_shop(tmp_path):
    import shutil
    import yaml
    from tools.whitebox import api_tests, extract
    d = tmp_path / "p"
    (d / "test_comprehension").mkdir(parents=True)
    for n in ("app_map", "api_inventory", "requirements", "form_model"):
        shutil.copy(f"application_assets/projects/bench_buggy_shop/test_comprehension/{n}.json", d / "test_comprehension")
    cfg = {"environment": "local", "safety": {"allow_destructive": True}, "test_types": {"api": True},
           "white_box": {"enabled": True, "source_dir": str(Path("benchmarks/apps/buggy_shop").resolve())},
           "auth": {"roles": {"user": {"steps": []}, "admin": {"steps": []}, "guest": {"anonymous": True}}},
           "api_tests": {"ownership": [{"path": "/api/orders/1", "owner": "admin", "other": "user"}]}}
    (d / "project.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    extract.run(d, root=Path(".").resolve())
    files, stats = api_tests.generate(d)
    assert stats["endpoint_coverage_pct"] >= 90
    text = "\n".join(f.read_text(encoding="utf-8") for f in files)
    assert "price below min (-0.01) -> rejected [benchmarks/apps/buggy_shop/app.py:99]" in text
    assert "POST /api/products — signed out -> 401" in text and "@AC-01.6" in text
    assert "GET /admin — as user (needs admin) -> 403" in text
    assert "/api/orders/1 as user (owned by admin) -> denied" in text
    assert "PUT is not allowed -> 405" in text
    assert "GET /api/products — unusual query values never 5xx" in text and "'100%'" in text
    assert "quantity at min 1 -> accepted" in text and "test.skip(\"POST /cart/add — quantity at min 1" in text
    assert "name at max length 50 -> accepted" in text and "status: 422" not in text
    counts = api_tests.register(d, files)
    plans = json.loads((d / "test_creation" / "test_plans.json").read_text(encoding="utf-8"))
    plans = plans.get("plans", plans)
    assert sum(counts.values()) == sum(len(p["tests"]) for k, p in plans.items() if k.startswith("API_"))


def test_api_generator_skips_data_changes_when_not_allowed(tmp_path):
    import shutil
    import yaml
    from tools.whitebox import api_tests, extract
    d = tmp_path / "p"
    (d / "test_comprehension").mkdir(parents=True)
    shutil.copy("application_assets/projects/bench_buggy_shop/test_comprehension/app_map.json", d / "test_comprehension")
    (d / "project.yaml").write_text(yaml.safe_dump({
        "environment": "prod", "test_types": {"api": True},
        "white_box": {"enabled": True, "source_dir": str(Path("benchmarks/apps/buggy_shop").resolve())}}), encoding="utf-8")
    extract.run(d, root=Path(".").resolve())
    files, _ = api_tests.generate(d)
    text = "\n".join(f.read_text(encoding="utf-8") for f in files)
    assert 'test.skip("POST /api/products — valid request is accepted' in text
    assert 'test("POST /api/products — price below min' in text           # rejection cases change nothing: they run
