# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import hashlib
import json
from dataclasses import dataclass
SPEND_SETTLED = 'settled'
SPEND_REFUSED = 'refused'
SPEND_HELD = 'held'
ARTIFACT_VERIFIED = 'verified'
ARTIFACT_UNVERIFIED = 'unverified'
ARTIFACT_ABSENT = 'absent'
ARTIFACT_FORECLOSED = 'foreclosed'
ARTIFACT_STATES = (ARTIFACT_VERIFIED, ARTIFACT_UNVERIFIED, ARTIFACT_ABSENT, ARTIFACT_FORECLOSED)
VERDICT_IN_REMIT = 'in_remit'
VERDICT_OUT_OF_REMIT = 'out_of_remit'
VERDICT_UNDETERMINED = 'undetermined'
VERDICTS = (VERDICT_IN_REMIT, VERDICT_OUT_OF_REMIT, VERDICT_UNDETERMINED)
OUTCOME_ALLOWED = 'allowed'
OUTCOME_REFUSED = 'refused'
DEFAULT_REFUND = 'refund'
DEFAULT_RELEASE = 'release'
DEFAULTS_VOCAB = (DEFAULT_REFUND, DEFAULT_RELEASE)
RULE_REFLEX = 'reflex'
RULE_JUDGMENT = 'judgment'
RULE_TYPES = (RULE_REFLEX, RULE_JUDGMENT)
DAY_SECONDS = 86400
REQUIRED_DEFAULTS = ('on_deadline', 'on_undetermined', 'response_window_seconds', 'hold_deadline_seconds', 'clawback_window_seconds')
PREDICATES_INT = ('amount_lte', 'amount_gte', 'daily_total_lte', 'daily_total_gte')
PREDICATES_WINDOW_AMOUNT = ('window_total_lte', 'window_total_gte', 'recipient_total_lte', 'recipient_total_gte')
PREDICATES_WINDOW_COUNT = ('spend_count_lte', 'spend_count_gte', 'recipient_count_lte', 'recipient_count_gte')
PREDICATES_LIST_NAME = ('recipient_in', 'recipient_not_in')
PREDICATES_STR_SET = ('category_in', 'category_not_in')
PREDICATES = PREDICATES_INT + PREDICATES_WINDOW_AMOUNT + PREDICATES_WINDOW_COUNT + PREDICATES_LIST_NAME + PREDICATES_STR_SET

class RemitError(ValueError):
 pass

@dataclass(frozen=True)
class Spend:
 amount: int
 recipient: str
 category: str
 at: int

def _require_int(value, context):
 if isinstance(value, bool) or not isinstance(value, int):
  raise RemitError('%s: expected int, got %r' % (context, type(value).__name__))
 if value < 0:
  raise RemitError('%s: expected non-negative, got %d' % (context, value))
 return value

def _require_str(value, context):
 if not isinstance(value, str) or value == '':
  raise RemitError('%s: expected non-empty str' % context)
 return value

def _require_one_of(value, allowed, context):
 if value not in allowed:
  raise RemitError('%s: expected one of %s, got %r' % (context, list(allowed), value))
 return value

def normalize_address(value, context='address'):
 _b = _require_str(value, context).strip().lower()
 if not _b.startswith('0x') or len(_b) < 3:
  raise RemitError('%s: not an address: %r' % (context, value))
 for ch in _b[2:]:
  if ch not in '0123456789abcdef':
   raise RemitError('%s: not hex: %r' % (context, value))
 return _b

def _window_slice(history, seconds, now):
 _a = now - _require_int(seconds, 'window seconds')
 return [h for h in history if _a < h.at <= now]

def window_total(spend, history, seconds, now):
 return spend.amount + sum((h.amount for h in _window_slice(history, seconds, now)))

def window_count(spend, history, seconds, now):
 return 1 + len(_window_slice(history, seconds, now))

def is_category(value):
 _b = str(value)
 if len(_b) < 1 or len(_b) > 40:
  return False
 for ch in _b:
  if not (ch.isascii() and (ch.isalnum() or ch in ' _.-')):
   return False
 return True

def same_recipient(spend, history):
 _b = normalize_address(spend.recipient, 'recipient')
 return [h for h in history if normalize_address(h.recipient, 'recipient') == _b]

def sole_predicate(obj, context):
 if not isinstance(obj, dict):
  raise RemitError('%s: expected an object' % context)
 if len(obj) != 1:
  raise RemitError('%s: expected exactly 1 predicate, got %d' % (context, len(obj)))
 _a = list(obj)[0]
 return (_a, obj[_a])

def _window_operand(operand, amount_key, context):
 if not isinstance(operand, dict):
  raise RemitError('%s: expected an object operand' % context)
 if amount_key not in operand or 'seconds' not in operand:
  raise RemitError("%s: operand needs %r and 'seconds'" % (context, amount_key))
 return (_require_int(operand[amount_key], context + '.' + amount_key), _require_int(operand['seconds'], context + '.seconds'))

def evaluate_predicate(name, operand, spend, history, vendor_lists):
 _d = 'predicate ' + str(name)
 if name not in PREDICATES:
  raise RemitError('%s: outside the v1 vocabulary' % _d)
 if name == 'amount_lte':
  return spend.amount <= _require_int(operand, _d)
 if name == 'amount_gte':
  return spend.amount >= _require_int(operand, _d)
 if name == 'daily_total_lte':
  return window_total(spend, history, DAY_SECONDS, spend.at) <= _require_int(operand, _d)
 if name == 'daily_total_gte':
  return window_total(spend, history, DAY_SECONDS, spend.at) >= _require_int(operand, _d)
 if name.startswith('recipient_') and name not in PREDICATES_LIST_NAME:
  history = same_recipient(spend, history)
 if name in PREDICATES_WINDOW_AMOUNT:
  _e, _i = _window_operand(operand, 'amount', _d)
  _j = window_total(spend, history, _i, spend.at)
  return _j <= _e if name.endswith('_lte') else _j >= _e
 if name in PREDICATES_WINDOW_COUNT:
  _e, _i = _window_operand(operand, 'count', _d)
  _c = window_count(spend, history, _i, spend.at)
  return _c <= _e if name.endswith('_lte') else _c >= _e
 if name in PREDICATES_LIST_NAME:
  _f = _require_str(operand, _d)
  if _f not in vendor_lists:
   raise RemitError('%s: vendor list %r is not defined' % (_d, _f))
  _g = [normalize_address(a, _d) for a in vendor_lists[_f]]
  _h = normalize_address(spend.recipient, _d) in _g
  return _h if name == 'recipient_in' else not _h
 if name in PREDICATES_STR_SET:
  if not isinstance(operand, (list, tuple)):
   raise RemitError('%s: expected a list operand' % _d)
  _g = [_require_str(c, _d) for c in operand]
  _h = spend.category in _g
  return _h if name == 'category_in' else not _h
 raise RemitError('%s: unhandled predicate' % _d)

def classify_spend(mandate, spend, history):
 _f = mandate.get('vendor_lists', {})
 _e = mandate.get('rules', [])
 for _d in _e:
  if _d.get('type') != RULE_REFLEX:
   continue
  _b, _c = sole_predicate(_d.get('check'), 'rule %s check' % _d.get('id'))
  if not evaluate_predicate(_b, _c, spend, history, _f):
   return (SPEND_REFUSED, [_d['id']])
 _a = []
 for _d in _e:
  if _d.get('type') != RULE_JUDGMENT:
   continue
  _b, _c = sole_predicate(_d.get('when'), 'rule %s when' % _d.get('id'))
  if evaluate_predicate(_b, _c, spend, history, _f):
   _a.append(_d['id'])
 if _a:
  return (SPEND_HELD, _a)
 return (SPEND_SETTLED, [])

def uncommitted_artifact(*, held_at, now, response_window_seconds):
 held_at = _require_int(held_at, 'held_at')
 now = _require_int(now, 'now')
 _a = _require_int(response_window_seconds, 'response_window_seconds')
 if now < held_at:
  raise RemitError('now %d precedes held_at %d' % (now, held_at))
 return ARTIFACT_FORECLOSED if now - held_at < _a else ARTIFACT_ABSENT

def _outcome_from_default(token, context):
 _require_one_of(token, DEFAULTS_VOCAB, context)
 return OUTCOME_REFUSED if token == DEFAULT_REFUND else OUTCOME_ALLOWED

def resolve_hold(*, verdict, artifact, requires_artifact, defaults, deadline_reached):
 _require_one_of(artifact, ARTIFACT_STATES, 'artifact state')
 for _a in REQUIRED_DEFAULTS:
  if _a not in defaults:
   raise RemitError('defaults: missing %r' % _a)
 if artifact == ARTIFACT_FORECLOSED:
  return OUTCOME_ALLOWED
 if verdict is None:
  if deadline_reached:
   return _outcome_from_default(defaults['on_deadline'], 'defaults.on_deadline')
  raise RemitError('no verdict and deadline not reached: case is not resolvable yet')
 _require_one_of(verdict, VERDICTS, 'verdict')
 if requires_artifact and artifact in (ARTIFACT_ABSENT, ARTIFACT_UNVERIFIED):
  return OUTCOME_REFUSED
 if verdict == VERDICT_IN_REMIT:
  return OUTCOME_ALLOWED
 if verdict == VERDICT_OUT_OF_REMIT:
  return OUTCOME_REFUSED
 return _outcome_from_default(defaults['on_undetermined'], 'defaults.on_undetermined')

def validate_mandate(mandate, *, stored_version, max_tier):
 _d = []

 def bad(message):
  _d.append(message)
 if not isinstance(mandate, dict):
  return ['mandate: expected an object']
 _u = mandate.get('version')
 if isinstance(_u, bool) or not isinstance(_u, int):
  bad('version: expected int')
 elif _u <= stored_version:
  bad('version: %r does not exceed stored version %r' % (_u, stored_version))
 _c = mandate.get('defaults')
 if not isinstance(_c, dict):
  bad('defaults: expected an object')
  _c = {}
 for _i in REQUIRED_DEFAULTS:
  if _i not in _c:
   bad('defaults: missing %r' % _i)
 for _i in ('on_deadline', 'on_undetermined'):
  if _i in _c and _c[_i] not in DEFAULTS_VOCAB:
   bad('defaults.%s: expected one of %s' % (_i, list(DEFAULTS_VOCAB)))
 for _i in ('response_window_seconds', 'hold_deadline_seconds', 'clawback_window_seconds'):
  if _i in _c:
   try:
    _require_int(_c[_i], 'defaults.' + _i)
   except RemitError as _e:
    bad(str(_e))
 if 'response_window_seconds' in _c and 'hold_deadline_seconds' in _c:
  try:
   _w = _require_int(_c['response_window_seconds'], 'w')
   _b = _require_int(_c['hold_deadline_seconds'], 'd')
   if _w >= _b:
    bad('defaults: response_window_seconds must be less than hold_deadline_seconds')
  except RemitError:
   pass
 _t = mandate.get('vendor_lists', {})
 if not isinstance(_t, dict):
  bad('vendor_lists: expected an object')
  _t = {}
 for _k in _t:
  if not isinstance(_t[_k], (list, tuple)):
   bad('vendor_lists.%s: expected a list' % _k)
   continue
  for _a in _t[_k]:
   try:
    normalize_address(_a, 'vendor_lists.' + str(_k))
   except RemitError as _e:
    bad(str(_e))
 _q = mandate.get('rules')
 if not isinstance(_q, (list, tuple)):
  return _d + ['rules: expected a list']
 _r = set()
 for _h, _n in enumerate(_q):
  _v = 'rules[%d]' % _h
  if not isinstance(_n, dict):
   bad('%s: expected an object' % _v)
   continue
  _o = _n.get('id')
  if not isinstance(_o, str) or _o == '':
   bad('%s.id: expected a non-empty string' % _v)
  elif _o in _r:
   bad('%s.id: duplicate rule id %r' % (_v, _o))
  else:
   _r.add(_o)
  _p = _n.get('type')
  if _p not in RULE_TYPES:
   bad('%s.type: expected one of %s' % (_v, list(RULE_TYPES)))
   continue
  _i = 'check' if _p == RULE_REFLEX else 'when'
  try:
   _k, _m = sole_predicate(_n.get(_i), '%s.%s' % (_v, _i))
   if _k not in PREDICATES:
    bad('%s.%s: predicate %r is outside the v1 vocabulary' % (_v, _i, _k))
   elif _k in PREDICATES_INT:
    _require_int(_m, '%s.%s.%s' % (_v, _i, _k))
   elif _k in PREDICATES_WINDOW_AMOUNT:
    _window_operand(_m, 'amount', '%s.%s.%s' % (_v, _i, _k))
   elif _k in PREDICATES_WINDOW_COUNT:
    _window_operand(_m, 'count', '%s.%s.%s' % (_v, _i, _k))
   elif _k in PREDICATES_LIST_NAME:
    _j = _require_str(_m, '%s.%s' % (_v, _i))
    if _j not in _t:
     bad('%s.%s: vendor list %r is not defined' % (_v, _i, _j))
   elif _k in PREDICATES_STR_SET:
    if not isinstance(_m, (list, tuple)) or not _m:
     bad('%s.%s.%s: expected a non-empty list' % (_v, _i, _k))
  except RemitError as _e:
   bad(str(_e))
  if _p == RULE_JUDGMENT:
   if not isinstance(_n.get('ask'), str) or not _n.get('ask'):
    bad('%s.ask: expected a non-empty string' % _v)
   _l = _n.get('on_breach')
   if not isinstance(_l, dict) or 'tier' not in _l:
    bad("%s.on_breach: expected an object with 'tier'" % _v)
   else:
    try:
     _s = _require_int(_l['tier'], '%s.on_breach.tier' % _v)
     if _s > max_tier:
      bad('%s.on_breach.tier: %d exceeds registered max_tier %d' % (_v, _s, max_tier))
    except RemitError as _e:
     bad(str(_e))
   if _n.get('requires_artifact') and (not isinstance(_n.get('requires_artifact'), bool)):
    bad('%s.requires_artifact: expected a bool' % _v)
   _g = bool(_n.get('context_uri'))
   _f = bool(_n.get('context_digest'))
   if _g != _f:
    bad('%s: context_uri and context_digest must be given together' % _v)
 return _d

def _rule_view(rule):
 _e = str(rule['type'])
 _d = rule['check'] if _e == RULE_REFLEX else rule['when']
 _f, _g = sole_predicate(_d, 'rule ' + str(rule['id']))
 a, b, s = (0, 0, '')
 if _f in PREDICATES_INT:
  a = int(_g)
 elif _f in PREDICATES_WINDOW_AMOUNT:
  a, b = (int(_g['amount']), int(_g['seconds']))
 elif _f in PREDICATES_WINDOW_COUNT:
  a, b = (int(_g['count']), int(_g['seconds']))
 elif _f in PREDICATES_LIST_NAME:
  s = str(_g)
 else:
  s = ','.join([str(c) for c in _g])
 return {'id': str(rule['id']), 'type': _e, 'predicate': _f, 'cond': {_f: _g}, 'a': a, 'b': b, 's': s, 'requires_artifact': bool(rule.get('requires_artifact', False)), 'tier': int(rule.get('on_breach', {}).get('tier', 0)), 'ask': str(rule.get('ask', ''))}

def api_compile(mandate_json, max_tier):
 try:
  _e = json.loads(mandate_json)
 except Exception:
  return json.dumps({'errors': ['mandate: not valid JSON']})
 _b = validate_mandate(_e, stored_version=0, max_tier=int(max_tier))
 if _b:
  return json.dumps({'errors': _b})
 _d = {}
 for _f in _e.get('vendor_lists', {}):
  _d[str(_f)] = [normalize_address(a) for a in _e['vendor_lists'][_f]]
 return json.dumps({'errors': [], 'mandate_version': int(_e['version']), 'mandate_uri': str(_e.get('mandate_uri', '')), 'mandate_digest': str(_e.get('mandate_digest', '')).lower(), 'defaults': {k: _e['defaults'][k] for k in REQUIRED_DEFAULTS}, 'vendor_lists': _d, 'rules': [_rule_view(r) for r in _e['rules']]})

def _mandate_of(compiled):
 _b = []
 for r in compiled['rules']:
  _b.append({'id': r['id'], 'type': r['type'], 'check' if r['type'] == RULE_REFLEX else 'when': r['cond']})
 return {'rules': _b, 'vendor_lists': compiled['vendor_lists']}

def _spend_of(row):
 return Spend(amount=int(row[0]), recipient=str(row[1]), category=str(row[2]), at=int(row[3]))

def api_classify(compiled_json, history_json, candidate_json):
 _b = json.loads(compiled_json)
 _a = json.loads(candidate_json)
 if not is_category(_a[2]):
  return json.dumps({'error': "category must be 1-40 letters, digits, spaces, '_', '.' or '-'", 'state': 'invalid', 'rules': []})
 _f, _c = classify_spend(_mandate_of(_b), _spend_of(_a), [_spend_of(h) for h in json.loads(history_json)])
 return json.dumps({'state': _f, 'rules': [str(r) for r in _c]})

def api_outcomes(compiled_json, requires_artifact):
 _b = json.loads(compiled_json)
 _c = {}
 for _d in VERDICTS:
  _c[_d] = {}
  for _a in ARTIFACT_STATES:
   _c[_d][_a] = resolve_hold(verdict=_d, artifact=_a, requires_artifact=bool(requires_artifact), defaults=_b['defaults'], deadline_reached=False)
 _c['deadline'] = {}
 for _a in ARTIFACT_STATES:
  _c['deadline'][_a] = resolve_hold(verdict=None, artifact=_a, requires_artifact=bool(requires_artifact), defaults=_b['defaults'], deadline_reached=True)
 return json.dumps(_c)

def api_uncommitted(held_at, now, window):
 return uncommitted_artifact(held_at=int(held_at), now=int(now), response_window_seconds=int(window))

class RemitEngine(gl.Contract):
 release: str
 prompts: Address

 def __init__(self, prompts: str):
  self.release = 'remit-engine/2'
  self.prompts = Address(prompts)

 @gl.public.view
 def compile_mandate(self, mandate_json: str, max_tier: int) -> str:
  return api_compile(str(mandate_json), int(max_tier))

 @gl.public.view
 def classify(self, compiled: str, history: str, candidate: str) -> str:
  return api_classify(str(compiled), str(history), str(candidate))

 @gl.public.view
 def outcomes(self, compiled: str, requires_artifact: bool) -> str:
  return api_outcomes(str(compiled), bool(requires_artifact))

 @gl.public.view
 def uncommitted(self, held_at: int, now: int, window: int) -> str:
  return api_uncommitted(int(held_at), int(now), int(window))

 @gl.public.view
 def prompts_address(self) -> str:
  return str(self.prompts)

 @gl.public.view
 def version(self) -> str:
  return self.release
