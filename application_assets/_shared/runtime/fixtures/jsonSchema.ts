// jsonSchema.ts — the JSON Schema subset verifyResponseSchema checks (Phase 5.1). No dependency (ajv is not installed).
//
// Supported keywords: type (string or list; "integer" too), required, properties, additionalProperties: false,
// items (one schema), enum, const, minimum, maximum, minLength, maxLength, pattern, minItems, maxItems.
// Unknown keywords are ignored, so a full OpenAPI schema still works as far as this subset reaches.

export type Schema = Record<string, any>;

function typeOf(v: unknown): string {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number';
  return typeof v;
}

function typeMatches(v: unknown, want: string): boolean {
  const got = typeOf(v);
  return got === want || (want === 'number' && got === 'integer');
}

/** Every violation as "<path>: <problem>"; [] = valid. */
export function validateSchema(value: unknown, schema: Schema, path = '$'): string[] {
  if (!schema || typeof schema !== 'object') return [];
  const errs: string[] = [];
  if (schema.type !== undefined) {
    const types: string[] = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!types.some((t) => typeMatches(value, t))) {
      return [`${path}: expected ${types.join('|')}, got ${typeOf(value)}`];
    }
  }
  if (schema.const !== undefined && JSON.stringify(value) !== JSON.stringify(schema.const)) {
    errs.push(`${path}: expected const ${JSON.stringify(schema.const)}`);
  }
  if (Array.isArray(schema.enum) && !schema.enum.some((e: unknown) => JSON.stringify(e) === JSON.stringify(value))) {
    errs.push(`${path}: ${JSON.stringify(value)} not in enum ${JSON.stringify(schema.enum)}`);
  }
  if (typeof value === 'number') {
    if (typeof schema.minimum === 'number' && value < schema.minimum) errs.push(`${path}: ${value} < minimum ${schema.minimum}`);
    if (typeof schema.maximum === 'number' && value > schema.maximum) errs.push(`${path}: ${value} > maximum ${schema.maximum}`);
  }
  if (typeof value === 'string') {
    if (typeof schema.minLength === 'number' && value.length < schema.minLength) errs.push(`${path}: shorter than ${schema.minLength}`);
    if (typeof schema.maxLength === 'number' && value.length > schema.maxLength) errs.push(`${path}: longer than ${schema.maxLength}`);
    if (typeof schema.pattern === 'string' && !new RegExp(schema.pattern).test(value)) errs.push(`${path}: does not match ${schema.pattern}`);
  }
  if (Array.isArray(value)) {
    if (typeof schema.minItems === 'number' && value.length < schema.minItems) errs.push(`${path}: fewer than ${schema.minItems} items`);
    if (typeof schema.maxItems === 'number' && value.length > schema.maxItems) errs.push(`${path}: more than ${schema.maxItems} items`);
    if (schema.items && typeof schema.items === 'object') {
      value.forEach((item, i) => errs.push(...validateSchema(item, schema.items, `${path}[${i}]`)));
    }
  }
  if (typeOf(value) === 'object') {
    const obj = value as Record<string, unknown>;
    for (const key of Array.isArray(schema.required) ? schema.required : []) {
      if (!(key in obj)) errs.push(`${path}: missing required '${key}'`);
    }
    const props: Record<string, Schema> = schema.properties ?? {};
    for (const [key, sub] of Object.entries(props)) {
      if (key in obj) errs.push(...validateSchema(obj[key], sub, `${path}.${key}`));
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(obj)) if (!(key in props)) errs.push(`${path}: unexpected property '${key}'`);
    }
  }
  return errs;
}
