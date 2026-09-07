"""A small, strict JSON Schema validator covering the subset our schemas use.

Written rather than depended upon, for two reasons. The marketplace manifest
must be self-contained and the README must be able to say "no configuration
required": a build that only passes once someone pip-installs something is not
that. And the schemas are the anti-hallucination guard, so the thing that
enforces them should be readable in one sitting by whoever is reviewing the
guard.

Supported keywords, which is exactly what schemas/*.json use and no more:

    $ref (local "#/$defs/x" and sibling-file "name.schema.json"), type, enum,
    const, properties, required, additionalProperties (false, closing the
    object, or a schema every unlisted property must satisfy), items, minItems,
    maxItems, minLength, minimum, maximum, exclusiveMinimum, pattern

Anything else in a schema raises UnsupportedKeyword rather than being ignored.
A validator that silently skips a constraint is worse than no validator, since
it reports success it did not check.
"""

import re

SUPPORTED = {
    "$schema", "$id", "$defs", "title", "description", "$ref",
    "type", "enum", "const", "properties", "required", "additionalProperties",
    "items", "minItems", "maxItems", "minLength", "minimum", "maximum",
    "exclusiveMinimum", "pattern",
}

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class UnsupportedKeyword(Exception):
    """A schema used a keyword this validator does not implement."""


def _matches_type(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    expected = TYPES.get(name)
    if expected is None:
        raise UnsupportedKeyword("unknown type %r" % (name,))
    return isinstance(value, expected)


class Validator:
    """Validates instances against one schema, resolving refs within a registry.

    ``registry`` maps a filename such as ``finding.schema.json`` to its parsed
    schema, which is how the report schema reaches the finding schema.
    """

    def __init__(self, schema, registry=None):
        self.schema = schema
        self.registry = registry or {}
        self._audit(schema, "#")

    def _audit(self, node, path):
        """Refuse to run against a schema using a keyword we do not implement."""
        if isinstance(node, dict):
            for key, value in node.items():
                if path == "#" and key in ("$schema", "$id", "$defs"):
                    pass
                elif key not in SUPPORTED:
                    raise UnsupportedKeyword("%s uses unsupported keyword %r" % (path, key))
                if key == "additionalProperties":
                    if value is True:
                        raise UnsupportedKeyword(
                            "%s: additionalProperties must be false or a schema; true would "
                            "let an invented field through unchecked" % (path,)
                        )
                    if isinstance(value, dict):
                        self._audit(value, path + "/additionalProperties")
                if key in ("properties", "$defs"):
                    for sub, subschema in value.items():
                        self._audit(subschema, "%s/%s/%s" % (path, key, sub))
                elif key == "items":
                    self._audit(value, path + "/items")

    def _resolve(self, ref):
        if ref.startswith("#/"):
            node = self.schema
            for part in ref[2:].split("/"):
                node = node[part]
            return node, self
        if ref in self.registry:
            target = self.registry[ref]
            return target, Validator(target, self.registry)
        raise UnsupportedKeyword("cannot resolve $ref %r" % (ref,))

    def errors(self, instance):
        """Return a list of human-readable error strings. Empty means valid."""
        out = []
        self._validate(instance, self.schema, "$", out)
        return out

    def is_valid(self, instance):
        return not self.errors(instance)

    def _validate(self, value, schema, path, out):
        if "$ref" in schema:
            target, owner = self._resolve(schema["$ref"])
            owner._validate(value, target, path, out)
            return

        if "const" in schema and value != schema["const"]:
            out.append("%s: expected %r, got %r" % (path, schema["const"], value))
            return

        if "enum" in schema and value not in schema["enum"]:
            out.append("%s: %r is not one of %s" % (path, value, schema["enum"]))
            return

        if "type" in schema:
            names = schema["type"]
            if isinstance(names, str):
                names = [names]
            if not any(_matches_type(value, n) for n in names):
                out.append("%s: expected type %s, got %s"
                           % (path, "/".join(names), type(value).__name__))
                return

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                out.append("%s: string shorter than minLength %d" % (path, schema["minLength"]))
            if "pattern" in schema and not re.search(schema["pattern"], value):
                out.append("%s: %r does not match %s" % (path, value, schema["pattern"]))

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                out.append("%s: %r is below minimum %r" % (path, value, schema["minimum"]))
            if "maximum" in schema and value > schema["maximum"]:
                out.append("%s: %r is above maximum %r" % (path, value, schema["maximum"]))
            if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
                out.append("%s: %r is not above exclusiveMinimum %r"
                           % (path, value, schema["exclusiveMinimum"]))

        if isinstance(value, dict):
            props = schema.get("properties", {})
            for name in schema.get("required", []):
                if name not in value:
                    out.append("%s: missing required property %r" % (path, name))
            extra = schema.get("additionalProperties")
            if extra is False and props:
                for name in value:
                    if name not in props:
                        out.append("%s: unknown property %r" % (path, name))
            elif isinstance(extra, dict):
                for name in sorted(value):
                    if name not in props:
                        self._validate(value[name], extra, "%s.%s" % (path, name), out)
            for name, subschema in props.items():
                if name in value:
                    self._validate(value[name], subschema, "%s.%s" % (path, name), out)

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                out.append("%s: fewer than minItems %d" % (path, schema["minItems"]))
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                out.append("%s: more than maxItems %d" % (path, schema["maxItems"]))
            if "items" in schema:
                for index, item in enumerate(value):
                    self._validate(item, schema["items"], "%s[%d]" % (path, index), out)


def resolve_field_path(schema, dotted, registry=None):
    """Resolve an evidence field path such as ``pages[].raw.text_len``.

    ``[]`` means "descend into this array's items". Returns the subschema, or
    raises KeyError naming the segment that does not exist. This is the check
    that makes fabricated evidence impossible: a rule naming a field the
    collector never produces fails the build.
    """
    registry = registry or {}
    node = schema
    walked = []

    def deref(n):
        seen = 0
        while isinstance(n, dict) and "$ref" in n:
            ref = n["$ref"]
            if ref.startswith("#/"):
                target = schema
                for part in ref[2:].split("/"):
                    target = target[part]
                n = target
            elif ref in registry:
                n = registry[ref]
            else:
                raise KeyError("unresolvable $ref %r at %s" % (ref, ".".join(walked) or "<root>"))
            seen += 1
            if seen > 20:
                raise KeyError("cyclic $ref at %s" % (".".join(walked) or "<root>",))
        return n

    for segment in dotted.split("."):
        array = segment.endswith("[]")
        name = segment[:-2] if array else segment
        node = deref(node)
        props = node.get("properties")
        if not props or name not in props:
            raise KeyError(
                "%r is not a field of %s" % (name, ".".join(walked) if walked else "<root>")
            )
        walked.append(segment)
        node = deref(props[name])
        if array:
            if node.get("type") != "array" or "items" not in node:
                raise KeyError("%s is not an array, so %r is wrong" % (".".join(walked), segment))
            node = deref(node["items"])
    return node
