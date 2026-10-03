# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import hashlib
import json
from dataclasses import dataclass
_A = 'settled'
_B = 'refused'
_C = 'held'
_D = 'verified'
_E = 'unverified'
_F = 'absent'
_G = 'foreclosed'
_H = (_D, _E, _F, _G)
_I = 'in_remit'
_J = 'out_of_remit'
_K = 'undetermined'
_L = (_I, _J, _K)
_M = 'allowed'
_N = 'refused'
_O = 'refund'
_P = 'release'
_Q = (_O, _P)
_R = 'reflex'
_S = 'judgment'
_T = (_R, _S)
_U = 86400
_V = 10000
_W = ('on_deadline', 'on_undetermined', 'response_window_seconds', 'hold_deadline_seconds', 'clawback_window_seconds')
_X = ('amount_lte', 'amount_gte', 'daily_total_lte', 'daily_total_gte')
_Y = ('window_total_lte', 'window_total_gte', 'recipient_total_lte', 'recipient_total_gte')
_Z = ('spend_count_lte', 'spend_count_gte', 'recipient_count_lte', 'recipient_count_gte')
_AA = ('recipient_in', 'recipient_not_in')
_AB = ('category_in', 'category_not_in')
_AC = _X + _Y + _Z + _AA + _AB

class _AD(ValueError):
 pass

@dataclass(frozen=True)
class Spend:
 amount: int
 recipient: str
 category: str
 at: int

@dataclass(frozen=True)
class BondPolicy:
 floor: int = 500
 bps: int = 1000
 escalation_factor: int = 2
 max_multiplier: int = 64
 decay_seconds: int = 604800
 appeal_multiplier: int = 2
 reward_bps: int = 500

def _AE(value, context):
 if isinstance(value, bool) or not isinstance(value, int):
  raise _AD('%s: expected int, got %r' % (context, type(value).__name__))
 if value < 0:
  raise _AD('%s: expected non-negative, got %d' % (context, value))
 return value

def _AF(value, context):
 if not isinstance(value, str) or value == '':
  raise _AD('%s: expected non-empty str' % context)
 return value

def _AG(value, allowed, context):
 if value not in allowed:
  raise _AD('%s: expected one of %s, got %r' % (context, list(allowed), value))
 return value

def _AH(credited, available, context):
 if credited != available:
  raise _AD('%s: value not conserved, credited %d against %d' % (context, credited, available))
 return credited

def _AI(value, context='address'):
 _b = _AF(value, context).strip().lower()
 if not _b.startswith('0x') or len(_b) < 3:
  raise _AD('%s: not an address: %r' % (context, value))
 for ch in _b[2:]:
  if ch not in '0123456789abcdef':
   raise _AD('%s: not hex: %r' % (context, value))
 return _b

def _AJ(history, seconds, now):
 _a = now - _AE(seconds, 'window seconds')
 return [h for h in history if _a < h.at <= now]

def _AK(spend, history, seconds, now):
 return spend.amount + sum((h.amount for h in _AJ(history, seconds, now)))

def _AL(spend, history, seconds, now):
 return 1 + len(_AJ(history, seconds, now))

def _AM(value):
 _b = str(value)
 if len(_b) < 1 or len(_b) > 40:
  return False
 for ch in _b:
  if not (ch.isascii() and (ch.isalnum() or ch in ' _.-')):
   return False
 return True

def _AN(spend, history):
 _b = _AI(spend.recipient, 'recipient')
 return [h for h in history if _AI(h.recipient, 'recipient') == _b]

def _AO(obj, context):
 if not isinstance(obj, dict):
  raise _AD('%s: expected an object' % context)
 if len(obj) != 1:
  raise _AD('%s: expected exactly 1 predicate, got %d' % (context, len(obj)))
 _a = list(obj)[0]
 return (_a, obj[_a])

def _AP(operand, amount_key, context):
 if not isinstance(operand, dict):
  raise _AD('%s: expected an object operand' % context)
 if amount_key not in operand or 'seconds' not in operand:
  raise _AD("%s: operand needs %r and 'seconds'" % (context, amount_key))
 return (_AE(operand[amount_key], context + '.' + amount_key), _AE(operand['seconds'], context + '.seconds'))

def _AQ(name, operand, spend, history, vendor_lists):
 _d = 'predicate ' + str(name)
 if name not in _AC:
  raise _AD('%s: outside the v1 vocabulary' % _d)
 if name == 'amount_lte':
  return spend.amount <= _AE(operand, _d)
 if name == 'amount_gte':
  return spend.amount >= _AE(operand, _d)
 if name == 'daily_total_lte':
  return _AK(spend, history, _U, spend.at) <= _AE(operand, _d)
 if name == 'daily_total_gte':
  return _AK(spend, history, _U, spend.at) >= _AE(operand, _d)
 if name.startswith('recipient_') and name not in _AA:
  history = _AN(spend, history)
 if name in _Y:
  _e, _i = _AP(operand, 'amount', _d)
  _j = _AK(spend, history, _i, spend.at)
  return _j <= _e if name.endswith('_lte') else _j >= _e
 if name in _Z:
  _e, _i = _AP(operand, 'count', _d)
  _c = _AL(spend, history, _i, spend.at)
  return _c <= _e if name.endswith('_lte') else _c >= _e
 if name in _AA:
  _f = _AF(operand, _d)
  if _f not in vendor_lists:
   raise _AD('%s: vendor list %r is not defined' % (_d, _f))
  _g = [_AI(a, _d) for a in vendor_lists[_f]]
  _h = _AI(spend.recipient, _d) in _g
  return _h if name == 'recipient_in' else not _h
 if name in _AB:
  if not isinstance(operand, (list, tuple)):
   raise _AD('%s: expected a list operand' % _d)
  _g = [_AF(c, _d) for c in operand]
  _h = spend.category in _g
  return _h if name == 'category_in' else not _h
 raise _AD('%s: unhandled predicate' % _d)

def _AR(mandate, spend, history):
 _f = mandate.get('vendor_lists', {})
 _e = mandate.get('rules', [])
 for _d in _e:
  if _d.get('type') != _R:
   continue
  _b, _c = _AO(_d.get('check'), 'rule %s check' % _d.get('id'))
  if not _AQ(_b, _c, spend, history, _f):
   return (_B, [_d['id']])
 _a = []
 for _d in _e:
  if _d.get('type') != _S:
   continue
  _b, _c = _AO(_d.get('when'), 'rule %s when' % _d.get('id'))
  if _AQ(_b, _c, spend, history, _f):
   _a.append(_d['id'])
 if _a:
  return (_C, _a)
 return (_A, [])

def _AS(*, held_at, now, response_window_seconds):
 held_at = _AE(held_at, 'held_at')
 now = _AE(now, 'now')
 _a = _AE(response_window_seconds, 'response_window_seconds')
 if now < held_at:
  raise _AD('now %d precedes held_at %d' % (now, held_at))
 return _G if now - held_at < _a else _F

def _AT(token, context):
 _AG(token, _Q, context)
 return _N if token == _O else _M

def _AU(*, verdict, artifact, requires_artifact, defaults, deadline_reached):
 _AG(artifact, _H, 'artifact state')
 for _a in _W:
  if _a not in defaults:
   raise _AD('defaults: missing %r' % _a)
 if artifact == _G:
  return _M
 if verdict is None:
  if deadline_reached:
   return _AT(defaults['on_deadline'], 'defaults.on_deadline')
  raise _AD('no verdict and deadline not reached: case is not resolvable yet')
 _AG(verdict, _L, 'verdict')
 if requires_artifact and artifact in (_F, _E):
  return _N
 if verdict == _I:
  return _M
 if verdict == _J:
  return _N
 return _AT(defaults['on_undetermined'], 'defaults.on_undetermined')

def _AV(*, losses, last_loss_at, now, policy):
 losses = _AE(losses, 'losses')
 if losses == 0:
  return 0
 last_loss_at = _AE(last_loss_at, 'last_loss_at')
 now = _AE(now, 'now')
 if now < last_loss_at:
  raise _AD('now %d precedes last_loss_at %d' % (now, last_loss_at))
 _a = (now - last_loss_at) // _AE(policy.decay_seconds, 'decay_seconds')
 return max(0, losses - _a)

def _AW(*, amount, losses, last_loss_at, now, policy):
 amount = _AE(amount, 'amount')
 _b = max(_AE(policy.floor, 'floor'), amount * _AE(policy.bps, 'bps') // _V)
 n = _AV(losses=losses, last_loss_at=last_loss_at, now=now, policy=policy)
 _e = 1
 _c = _AE(policy.max_multiplier, 'max_multiplier')
 _d = _AE(policy.escalation_factor, 'escalation_factor')
 if _d < 2:
  raise _AD('escalation_factor must be at least 2, got %d' % _d)
 for _ in range(n):
  _e *= _d
  if _e >= _c:
   _e = _c
   break
 return _b * _e

def _AX(*, refused_amount, agent_standing, policy):
 refused_amount = _AE(refused_amount, 'refused_amount')
 agent_standing = _AE(agent_standing, 'agent_standing')
 _a = refused_amount * _AE(policy.reward_bps, 'reward_bps') // _V
 return min(_a, agent_standing)
_AY = 'upheld'
_AZ = 'dismissed'
_BA = 2
_BB = 3

def _BC(*, spend, rule, challenger, agent, now, clawback_window_seconds):
 if spend.get('authorization') != 'authorized':
  return 'only an authorized payment can be challenged'
 if str(spend.get('verdict', '')) != '' or str(spend.get('reason', '')) != '':
  return 'this payment was decided by a jury or by the principal; appeal that decision instead'
 if rule is None or rule.get('type') != _S:
  return "a challenge must name one of the mandate's judgment rules"
 if _AI(challenger, 'challenger') == _AI(agent, 'agent'):
  return 'the agent cannot challenge its own payment'
 _a = int(spend.get('decided_at', 0))
 if _a <= 0 or now - _a > int(clawback_window_seconds):
  return 'the clawback window for this payment has closed'
 return ''

def _BD(*, verdict, bond, amount, paid, standing, policy):
 _AG(verdict, _L, 'verdict')
 bond = _AE(bond, 'bond')
 amount = _AE(amount, 'amount')
 standing = _AE(standing, 'standing')
 if verdict != _J:
  _b = {'state': _AZ, 'to_challenger': 0, 'to_agent': bond, 'to_treasury': 0, 'from_standing': 0, 'blocked': False}
  _AH(_b['to_challenger'] + _b['to_agent'], bond, 'resolve_challenge/dismissed')
  return _b
 _a = min(amount, standing) if paid else 0
 _c = _AX(refused_amount=amount, agent_standing=standing - _a, policy=policy)
 _b = {'state': _AY, 'to_challenger': bond + _c, 'to_agent': 0, 'to_treasury': _a, 'from_standing': _a + _c, 'blocked': not paid}
 _AH(_b['to_challenger'] + _b['to_treasury'], bond + _b['from_standing'], 'resolve_challenge/upheld')
 return _b

def _BE(*, losses, upheld, now):
 losses = _AE(losses, 'losses')
 if upheld:
  return (0, 0)
 return (losses + 1, _AE(now, 'now'))

def _BF(*, tier, shadow):
 tier = _AE(tier, 'tier')
 if shadow or tier < _BA:
  return 0
 return _BB if tier >= _BB else _BA

def _BG(mandate, *, stored_version, max_tier):
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
 for _i in _W:
  if _i not in _c:
   bad('defaults: missing %r' % _i)
 for _i in ('on_deadline', 'on_undetermined'):
  if _i in _c and _c[_i] not in _Q:
   bad('defaults.%s: expected one of %s' % (_i, list(_Q)))
 for _i in ('response_window_seconds', 'hold_deadline_seconds', 'clawback_window_seconds'):
  if _i in _c:
   try:
    _AE(_c[_i], 'defaults.' + _i)
   except _AD as _e:
    bad(str(_e))
 if 'response_window_seconds' in _c and 'hold_deadline_seconds' in _c:
  try:
   _w = _AE(_c['response_window_seconds'], 'w')
   _b = _AE(_c['hold_deadline_seconds'], 'd')
   if _w >= _b:
    bad('defaults: response_window_seconds must be less than hold_deadline_seconds')
  except _AD:
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
    _AI(_a, 'vendor_lists.' + str(_k))
   except _AD as _e:
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
  if _p not in _T:
   bad('%s.type: expected one of %s' % (_v, list(_T)))
   continue
  _i = 'check' if _p == _R else 'when'
  try:
   _k, _m = _AO(_n.get(_i), '%s.%s' % (_v, _i))
   if _k not in _AC:
    bad('%s.%s: predicate %r is outside the v1 vocabulary' % (_v, _i, _k))
   elif _k in _X:
    _AE(_m, '%s.%s.%s' % (_v, _i, _k))
   elif _k in _Y:
    _AP(_m, 'amount', '%s.%s.%s' % (_v, _i, _k))
   elif _k in _Z:
    _AP(_m, 'count', '%s.%s.%s' % (_v, _i, _k))
   elif _k in _AA:
    _j = _AF(_m, '%s.%s' % (_v, _i))
    if _j not in _t:
     bad('%s.%s: vendor list %r is not defined' % (_v, _i, _j))
   elif _k in _AB:
    if not isinstance(_m, (list, tuple)) or not _m:
     bad('%s.%s.%s: expected a non-empty list' % (_v, _i, _k))
  except _AD as _e:
   bad(str(_e))
  if _p == _S:
   if not isinstance(_n.get('ask'), str) or not _n.get('ask'):
    bad('%s.ask: expected a non-empty string' % _v)
   _l = _n.get('on_breach')
   if not isinstance(_l, dict) or 'tier' not in _l:
    bad("%s.on_breach: expected an object with 'tier'" % _v)
   else:
    try:
     _s = _AE(_l['tier'], '%s.on_breach.tier' % _v)
     if _s > max_tier:
      bad('%s.on_breach.tier: %d exceeds registered max_tier %d' % (_v, _s, max_tier))
    except _AD as _e:
     bad(str(_e))
   if _n.get('requires_artifact') and (not isinstance(_n.get('requires_artifact'), bool)):
    bad('%s.requires_artifact: expected a bool' % _v)
   _g = bool(_n.get('context_uri'))
   _f = bool(_n.get('context_digest'))
   if _g != _f:
    bad('%s: context_uri and context_digest must be given together' % _v)
 return _d

def _BH(rule):
 _e = str(rule['type'])
 _d = rule['check'] if _e == _R else rule['when']
 _f, _g = _AO(_d, 'rule ' + str(rule['id']))
 a, b, s = (0, 0, '')
 if _f in _X:
  a = int(_g)
 elif _f in _Y:
  a, b = (int(_g['amount']), int(_g['seconds']))
 elif _f in _Z:
  a, b = (int(_g['count']), int(_g['seconds']))
 elif _f in _AA:
  s = str(_g)
 else:
  s = ','.join([str(c) for c in _g])
 return {'id': str(rule['id']), 'type': _e, 'predicate': _f, 'cond': {_f: _g}, 'a': a, 'b': b, 's': s, 'requires_artifact': bool(rule.get('requires_artifact', False)), 'tier': int(rule.get('on_breach', {}).get('tier', 0)), 'ask': str(rule.get('ask', ''))}

def _BI(mandate_json, max_tier):
 try:
  _e = json.loads(mandate_json)
 except Exception:
  return json.dumps({'errors': ['mandate: not valid JSON']})
 _b = _BG(_e, stored_version=0, max_tier=int(max_tier))
 if _b:
  return json.dumps({'errors': _b})
 _d = {}
 for _f in _e.get('vendor_lists', {}):
  _d[str(_f)] = [_AI(a) for a in _e['vendor_lists'][_f]]
 return json.dumps({'errors': [], 'mandate_version': int(_e['version']), 'mandate_uri': str(_e.get('mandate_uri', '')), 'mandate_digest': str(_e.get('mandate_digest', '')).lower(), 'defaults': {k: _e['defaults'][k] for k in _W}, 'vendor_lists': _d, 'rules': [_BH(r) for r in _e['rules']]})

def _BJ(compiled):
 _b = []
 for r in compiled['rules']:
  _b.append({'id': r['id'], 'type': r['type'], 'check' if r['type'] == _R else 'when': r['cond']})
 return {'rules': _b, 'vendor_lists': compiled['vendor_lists']}

def _BK(row):
 return Spend(amount=int(row[0]), recipient=str(row[1]), category=str(row[2]), at=int(row[3]))

def _BL(compiled_json, history_json, candidate_json):
 _b = json.loads(compiled_json)
 _a = json.loads(candidate_json)
 if not _AM(_a[2]):
  return json.dumps({'error': "category must be 1-40 letters, digits, spaces, '_', '.' or '-'", 'state': 'invalid', 'rules': []})
 _f, _c = _AR(_BJ(_b), _BK(_a), [_BK(h) for h in json.loads(history_json)])
 return json.dumps({'state': _f, 'rules': [str(r) for r in _c]})

def _BM(compiled_json, requires_artifact):
 _b = json.loads(compiled_json)
 _c = {}
 for _d in _L:
  _c[_d] = {}
  for _a in _H:
   _c[_d][_a] = _AU(verdict=_d, artifact=_a, requires_artifact=bool(requires_artifact), defaults=_b['defaults'], deadline_reached=False)
 _c['deadline'] = {}
 for _a in _H:
  _c['deadline'][_a] = _AU(verdict=None, artifact=_a, requires_artifact=bool(requires_artifact), defaults=_b['defaults'], deadline_reached=True)
 return json.dumps(_c)

def _BN(held_at, now, window):
 return _AS(held_at=int(held_at), now=int(now), response_window_seconds=int(window))

def _BO(spend_json, rule_json, challenger, agent, now, window, losses, last_loss_at, floor):
 _c = json.loads(spend_json)
 _b = _BC(spend=_c, rule=json.loads(rule_json), challenger=str(challenger), agent=str(agent), now=int(now), clawback_window_seconds=int(window))
 _a = _AW(amount=int(_c['amount']), losses=int(losses), last_loss_at=int(last_loss_at), now=int(now), policy=BondPolicy(floor=int(floor)))
 return json.dumps({'error': _b, 'bond': _a})

def _BP(verdict, bond, amount, paid, standing, floor, losses, now, tier):
 _a = _BD(verdict=str(verdict), bond=int(bond), amount=int(amount), paid=bool(paid), standing=int(standing), policy=BondPolicy(floor=int(floor)))
 _b = _a['state'] == _AY
 _a['losses'], _a['last_loss_at'] = _BE(losses=int(losses), upheld=_b, now=int(now))
 _a['freeze'] = _BF(tier=int(tier), shadow=False) if _b else 0
 return json.dumps(_a)

class RemitEngine(gl.Contract):
 release: str
 prompts: Address

 def __init__(self, prompts: str):
  self.release = 'remit-engine/3'
  self.prompts = Address(prompts)

 @gl.public.view
 def compile_mandate(self, mandate_json: str, max_tier: int) -> str:
  return _BI(str(mandate_json), int(max_tier))

 @gl.public.view
 def classify(self, compiled: str, history: str, candidate: str) -> str:
  return _BL(str(compiled), str(history), str(candidate))

 @gl.public.view
 def outcomes(self, compiled: str, requires_artifact: bool) -> str:
  return _BM(str(compiled), bool(requires_artifact))

 @gl.public.view
 def uncommitted(self, held_at: int, now: int, window: int) -> str:
  return _BN(int(held_at), int(now), int(window))

 @gl.public.view
 def challenge_terms(self, spend: str, rule: str, challenger: str, agent: str, now: int, window: int, losses: int, last_loss_at: int, floor: int) -> str:
  return _BO(str(spend), str(rule), str(challenger), str(agent), int(now), int(window), int(losses), int(last_loss_at), int(floor))

 @gl.public.view
 def challenge_result(self, verdict: str, bond: int, amount: int, paid: bool, standing: int, floor: int, losses: int, now: int, tier: int) -> str:
  return _BP(str(verdict), int(bond), int(amount), bool(paid), int(standing), int(floor), int(losses), int(now), int(tier))

 @gl.public.view
 def prompts_address(self) -> str:
  return str(self.prompts)

 @gl.public.view
 def version(self) -> str:
  return self.release
