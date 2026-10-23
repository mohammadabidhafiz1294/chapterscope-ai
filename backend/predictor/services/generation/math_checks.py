"""Safe, deterministic mathematical verification for numerical answers (Phase 7).

Never uses unrestricted ``eval``. Every model-supplied expression is first
parsed with Python's :mod:`ast`, then translated node-by-node into SymPy
objects. Anything outside a small whitelist (arithmetic, comparisons, a few
named functions, and ``x``/``y``/``z`` symbols) is rejected before it ever
reaches SymPy.

Only a narrow set of problem kinds is independently recomputable:

``evaluate``   compute ``expression`` with the given ``assignments``.
``solve``      solve a linear ``equation`` (``a*x + b = c``) for ``variable``.
``compare``    check ``left`` vs ``right`` (``<``, ``<=``, ``>``, ``>=``, ``==``).
``equivalent`` check ``left`` and ``right`` are algebraically equal.

Anything else returns ``UNSUPPORTED`` and the caller marks the question
``needs_review`` rather than presenting it as verified. A wrong answer for a
supported kind returns ``MISMATCH`` -> also ``needs_review``.
"""

import ast
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

MAX_EXPRESSION_CHARS = 200
MAX_AST_NODES = 40
# Bounds that keep a crafted exponent from turning SymPy into a CPU/RAM sink.
MAX_LITERAL_ABS = 1_000_000
MAX_EXPONENT = 100

# Names allowed to appear as symbols. Kept tiny and inert.
_ALLOWED_NAMES = frozenset({'x', 'y', 'z', 'True', 'False'})

# Functions the model may use, mapped to SymPy equivalents.
_ALLOWED_FUNCTIONS = {
    'sqrt': 'sqrt',
    'log': 'log',
    'ln': 'log',
    'exp': 'exp',
    'Abs': 'Abs',
    'abs': 'Abs',
    'sin': 'sin',
    'cos': 'cos',
    'tan': 'tan',
    'pi': 'pi',
    'E': 'E',
}

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
}

_CMPOPS = {
    ast.Lt: '<',
    ast.LtE: '<=',
    ast.Gt: '>',
    ast.GtE: '>=',
    ast.Eq: '==',
}


class ParseRejected(Exception):
    """The expression used a construct outside the whitelist."""


def _check_length(text):
    if not isinstance(text, str) or not text.strip():
        raise ParseRejected('empty expression')
    if len(text) > MAX_EXPRESSION_CHARS:
        raise ParseRejected('expression too long')


def _walk(node, sympy, symbols, counter):
    """Translate a validated AST node into a SymPy object.

    ``counter`` is a one-element list used to bound the number of nodes we
    process, so a pathological tree cannot run unbounded.
    """
    counter[0] += 1
    if counter[0] > MAX_AST_NODES:
        raise ParseRejected('expression too complex')

    if isinstance(node, ast.Expression):
        return _walk(node.body, sympy, symbols, counter)

    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParseRejected('literal must be a number')
        if abs(value) > MAX_LITERAL_ABS:
            raise ParseRejected('literal too large')
        return sympy.Integer(value) if isinstance(value, int) else sympy.Float(value)

    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise ParseRejected('name not allowed')
        return symbols[node.id]

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_walk(node.operand, sympy, symbols, counter)

    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _walk(node.left, sympy, symbols, counter)
        right = _walk(node.right, sympy, symbols, counter)
        if isinstance(node.op, ast.Pow):
            # Only allow a modest numeric exponent; symbolic powers (x**2)
            # are fine because the caller never substitutes a huge value.
            if getattr(right, 'is_number', False):
                try:
                    if abs(float(right)) > MAX_EXPONENT:
                        raise ParseRejected('exponent too large')
                except (TypeError, ValueError, OverflowError):
                    raise ParseRejected('exponent not finite')
        return _BINOPS[type(node.op)](left, right)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ParseRejected('indirect call')
        if node.func.id not in _ALLOWED_FUNCTIONS:
            raise ParseRejected('function not allowed')
        if node.keywords:
            raise ParseRejected('keyword arguments not allowed')
        fn = getattr(sympy, _ALLOWED_FUNCTIONS[node.func.id])
        args = [_walk(arg, sympy, symbols, counter) for arg in node.args]
        return fn(*args)

    # Anything else (attribute access, subscripts, comprehensions, ...) is out.
    raise ParseRejected('construct not allowed')


def safe_sympify(text):
    """Parse ``text`` through the whitelisted AST walk into a SymPy object."""
    import sympy

    _check_length(text)
    try:
        tree = ast.parse(text.strip(), mode='eval')
    except SyntaxError as exc:
        raise ParseRejected('syntax error') from exc

    names = _ALLOWED_NAMES - {'True', 'False'}
    symbols = {name: sympy.Symbol(name) for name in names}
    symbols['True'] = sympy.Integer(1)
    symbols['False'] = sympy.Integer(0)
    return _walk(tree, sympy, symbols, [0])


def _to_number(value):
    """Best-effort real number from a SymPy object, or ``None``."""
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if as_float != as_float:  # NaN
        return None
    return as_float


def _tolerance():
    try:
        return float(getattr(settings, 'GENERATION_NUMERIC_TOLERANCE', 1e-6))
    except (TypeError, ValueError):
        return 1e-6


def _parse_assignments(raw):
    """Model-supplied ``{"x": "2"}`` -> validated ``{symbol: sympy}`` pairs."""
    out = {}
    for key, value in (raw or {}).items():
        key = str(key).strip()
        if key not in _ALLOWED_NAMES:
            raise ParseRejected('assignment target not allowed')
        out[key] = safe_sympify(str(value))
    return out


def verify_numeric(problem):
    """Independently recompute a supported problem; return a status dict.

    Never raises for a malformed problem: an unusable one yields
    ``status='UNPARSABLE'`` (or ``UNSUPPORTED``) so the caller marks the
    question needs_review instead of crashing the whole request.
    """
    import sympy

    kind = (problem.get('kind') or '').strip()
    tol = _tolerance()
    result = (problem.get('result') or '').strip()

    try:
        if kind == 'evaluate':
            expr = safe_sympify(problem.get('expression') or '')
            subs = _parse_assignments(problem.get('assignments'))
            if subs:
                expr = expr.subs(subs)
            expected = _to_number(sympy.simplify(expr))
            actual = _to_number(safe_sympify(result))
            if expected is None or actual is None:
                return {'status': 'UNPARSABLE'}
            ok = abs(expected - actual) <= max(tol, tol * abs(expected))
            return {
                'status': 'MATCH' if ok else 'MISMATCH',
                'expected': expected,
                'actual': actual,
            }

        if kind == 'solve':
            # Linear only: parse "a*x + b" and "c" around the '=' sign.
            equation = (problem.get('equation') or '').strip()
            if '=' not in equation:
                return {'status': 'UNPARSABLE'}
            left, right = equation.split('=', 1)
            lhs = safe_sympify(left)
            rhs = safe_sympify(right)
            variable = (problem.get('variable') or 'x').strip()
            if variable not in (_ALLOWED_NAMES - {'True', 'False'}):
                return {'status': 'UNSUPPORTED'}
            symbol = sympy.Symbol(variable)
            # Restrict to degree-1 polynomials so solve() cannot explore a
            # surprising (or slow) solution space.
            try:
                degree = sympy.Poly(sympy.expand(lhs - rhs), symbol).degree()
            except Exception:
                return {'status': 'UNSUPPORTED'}
            if degree != 1:
                return {'status': 'UNSUPPORTED'}
            sol = sympy.solve(sympy.Eq(lhs, rhs), symbol)
            if len(sol) != 1:
                return {'status': 'UNSUPPORTED'}
            expected = _to_number(sol[0])
            actual = _to_number(safe_sympify(result))
            if expected is None or actual is None:
                return {'status': 'UNPARSABLE'}
            ok = abs(expected - actual) <= max(tol, tol * abs(expected))
            return {
                'status': 'MATCH' if ok else 'MISMATCH',
                'expected': expected,
                'actual': actual,
            }

        if kind == 'compare':
            operator = (problem.get('operator') or '').strip()
            if operator not in _CMPOPS.values():
                return {'status': 'UNSUPPORTED'}
            left = _to_number(sympy.simplify(safe_sympify(problem.get('left') or '')))
            right = _to_number(sympy.simplify(safe_sympify(problem.get('right') or '')))
            if left is None or right is None:
                return {'status': 'UNPARSABLE'}
            expected = {
                '<': left < right,
                '<=': left <= right,
                '>': left > right,
                '>=': left >= right,
                '==': left == right,
            }[operator]
            actual = str(result).strip().lower() in ('true', '1', 'yes')
            return {'status': 'MATCH' if expected == actual else 'MISMATCH'}

        if kind == 'equivalent':
            left = sympy.simplify(safe_sympify(problem.get('left') or ''))
            right = sympy.simplify(safe_sympify(problem.get('right') or ''))
            # Algebraic equality: difference must be identically zero.
            difference = sympy.simplify(left - right)
            ok = difference == 0
            return {'status': 'MATCH' if ok else 'MISMATCH'}

        return {'status': 'UNSUPPORTED'}
    except ParseRejected:
        return {'status': 'UNPARSABLE'}
    except Exception:  # pragma: no cover - defensive; never crash the turn
        logger.info('numeric_check_failed kind=%s', kind)
        return {'status': 'UNPARSABLE'}
