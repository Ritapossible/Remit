#!/usr/bin/env python3
"""Minify a built contract for deployment.

Gas on Bradbury scales with the bytes of code in the deploy transaction. This
strips docstrings and comments, drops top-level definitions the contract class
can never reach, and re-indents to one space. It round-trips the syntax tree,
so every executable node that remains is preserved exactly;
tests/direct/test_split_build.py checks the deployed files against a fresh
minify of the readable builds.

The runner header is written first and followed IMMEDIATELY by code: a comment
line between them fails the deploy on every validator (CLAUDE.md, hard law 8).
Called by deploy/build_contract.py.
"""

import ast
import os
import sys



def strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _bound_in(fn):
    """Names a function binds itself: parameters and assignment targets. In
    Python these are local for the whole function body."""
    out = set()
    a = fn.args
    for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
        out.add(arg.arg)
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not fn:
            out.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
    return out


def _names_used(node, shadowed=frozenset()):
    """Global names a node can refer to. A name a function binds itself is a
    local there, not a reference to a top-level definition of the same name -
    otherwise a parameter called ``artifact_state`` keeps a function called
    ``artifact_state`` alive."""
    out = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        if not isinstance(node, ast.Lambda):
            shadowed = shadowed | _bound_in(node)
            for d in node.decorator_list + node.args.defaults + [x for x in node.args.kw_defaults if x]:
                out |= _names_used(d, shadowed)
            body = node.body
        else:
            shadowed = shadowed | {x.arg for x in node.args.args}
            body = [node.body]
        for child in body:
            out |= _names_used(child, shadowed)
        return out
    if isinstance(node, ast.Name):
        # Only a read is a reference; a store (an annotation target, an
        # assignment) defines a name rather than using one.
        return set() if node.id in shadowed or not isinstance(node.ctx, ast.Load) else {node.id}
    for child in ast.iter_child_nodes(node):
        out |= _names_used(child, shadowed)
    return out


def _defines(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def tree_shake(tree, root="RemitGuard"):
    """Drop top-level definitions the contract can never reach.

    Starts from the contract class and follows references transitively. The
    engine keeps functions the contract does not call (bond economics,
    challenge settlement, an off-chain classifier); they stay tested in
    remit_core.py and simply are not shipped.
    """
    defs = {}
    for node in tree.body:
        for name in _defines(node):
            defs[name] = node
    keep, frontier = set(), [root]
    while frontier:
        name = frontier.pop()
        if name in keep or name not in defs:
            continue
        keep.add(name)
        frontier.extend(_names_used(defs[name]))
    removed = sorted(n for n in defs if n not in keep)
    tree.body = [node for node in tree.body if not _defines(node) or (_defines(node) & keep)]
    return tree, removed


def rename_locals(tree):
    """Give each function's own local variables short names.

    Only names a function assigns itself are renamed - never a parameter
    (GenVM calls public methods by argument name), never a name that matches
    a module-level definition or a builtin (so no global read can be captured),
    and consistently across nested closures, which share their enclosing
    scope's names. Semantics are unchanged; tests/direct/test_split.py runs the
    minified contracts against the readable ones to prove it.
    """
    import builtins as _b

    module_names = set(dir(_b)) | {"gl", "Address", "u256", "TreeMap", "DynArray", "self"}
    for node in tree.body:
        module_names |= _defines(node)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module_names |= {(a.asname or a.name).split(".")[0] for a in node.names}

    def outermost_functions():
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        yield item

    for fn in outermost_functions():
        params, stored, declared = set(), set(), set()
        for n in ast.walk(fn):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                a = n.args
                params |= {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs + [y for y in (a.vararg, a.kwarg) if y]}
                if not isinstance(n, ast.Lambda) and n is not fn:
                    declared.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                stored.add(n.id)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                stored.add(n.name)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                declared |= set(n.names)
        targets = sorted(stored - params - declared - module_names)
        used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | params | declared | module_names
        mapping, i = {}, 0
        for name in targets:
            while True:
                short = "_%s" % _short(i)
                i += 1
                if short not in used:
                    break
            if len(short) < len(name):
                mapping[name] = short
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and n.id in mapping:
                n.id = mapping[n.id]
            elif isinstance(n, ast.ExceptHandler) and n.name in mapping:
                n.name = mapping[n.name]
    return tree


def _short(i):
    letters = "abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        out = letters[i % 26] + out
        i = i // 26 - 1
        if i < 0:
            return out


def reindent(code):
    """Four-space indentation to one space. Safe on ast.unparse output: it
    never continues a statement onto another line, so leading whitespace is
    always indentation and always a multiple of four."""
    lines = []
    for line in code.splitlines():
        stripped = line.lstrip(" ")
        depth = len(line) - len(stripped)
        if depth % 4:
            raise SystemExit("unexpected indentation: %r" % line[:60])
        lines.append(" " * (depth // 4) + stripped)
    return "\n".join(lines)


def minify(source, shake=True, root="RemitGuard"):
    header = source.splitlines()[0]
    if not header.startswith('# { "Depends":'):
        raise SystemExit("build does not start with the runner header")
    tree = strip_docstrings(ast.parse(source))
    removed = []
    if shake:
        tree, removed = tree_shake(tree, root=root)
    tree = rename_locals(tree)
    return header + "\n" + reindent(ast.unparse(tree)) + "\n", removed


if __name__ == "__main__":
    sys.exit("run deploy/build_contract.py, which builds and minifies both contracts")
