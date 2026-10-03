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
 text = _require_str(value, context).strip().lower()
 if not text.startswith('0x') or len(text) < 3:
  raise RemitError('%s: not an address: %r' % (context, value))
 for ch in text[2:]:
  if ch not in '0123456789abcdef':
   raise RemitError('%s: not hex: %r' % (context, value))
 return text

def _window_slice(history, seconds, now):
 floor_at = now - _require_int(seconds, 'window seconds')
 return [h for h in history if floor_at < h.at <= now]

def window_total(spend, history, seconds, now):
 return spend.amount + sum((h.amount for h in _window_slice(history, seconds, now)))

def window_count(spend, history, seconds, now):
 return 1 + len(_window_slice(history, seconds, now))

def same_recipient(spend, history):
 mine = normalize_address(spend.recipient, 'recipient')
 return [h for h in history if normalize_address(h.recipient, 'recipient') == mine]

def sole_predicate(obj, context):
 if not isinstance(obj, dict):
  raise RemitError('%s: expected an object' % context)
 if len(obj) != 1:
  raise RemitError('%s: expected exactly 1 predicate, got %d' % (context, len(obj)))
 name = list(obj)[0]
 return (name, obj[name])

def _window_operand(operand, amount_key, context):
 if not isinstance(operand, dict):
  raise RemitError('%s: expected an object operand' % context)
 if amount_key not in operand or 'seconds' not in operand:
  raise RemitError("%s: operand needs %r and 'seconds'" % (context, amount_key))
 return (_require_int(operand[amount_key], context + '.' + amount_key), _require_int(operand['seconds'], context + '.seconds'))

def evaluate_predicate(name, operand, spend, history, vendor_lists):
 ctx = 'predicate ' + str(name)
 if name not in PREDICATES:
  raise RemitError('%s: outside the v1 vocabulary' % ctx)
 if name == 'amount_lte':
  return spend.amount <= _require_int(operand, ctx)
 if name == 'amount_gte':
  return spend.amount >= _require_int(operand, ctx)
 if name == 'daily_total_lte':
  return window_total(spend, history, DAY_SECONDS, spend.at) <= _require_int(operand, ctx)
 if name == 'daily_total_gte':
  return window_total(spend, history, DAY_SECONDS, spend.at) >= _require_int(operand, ctx)
 if name.startswith('recipient_') and name not in PREDICATES_LIST_NAME:
  history = same_recipient(spend, history)
 if name in PREDICATES_WINDOW_AMOUNT:
  limit, seconds = _window_operand(operand, 'amount', ctx)
  total = window_total(spend, history, seconds, spend.at)
  return total <= limit if name.endswith('_lte') else total >= limit
 if name in PREDICATES_WINDOW_COUNT:
  limit, seconds = _window_operand(operand, 'count', ctx)
  count = window_count(spend, history, seconds, spend.at)
  return count <= limit if name.endswith('_lte') else count >= limit
 if name in PREDICATES_LIST_NAME:
  list_name = _require_str(operand, ctx)
  if list_name not in vendor_lists:
   raise RemitError('%s: vendor list %r is not defined' % (ctx, list_name))
  members = [normalize_address(a, ctx) for a in vendor_lists[list_name]]
  present = normalize_address(spend.recipient, ctx) in members
  return present if name == 'recipient_in' else not present
 if name in PREDICATES_STR_SET:
  if not isinstance(operand, (list, tuple)):
   raise RemitError('%s: expected a list operand' % ctx)
  members = [_require_str(c, ctx) for c in operand]
  present = spend.category in members
  return present if name == 'category_in' else not present
 raise RemitError('%s: unhandled predicate' % ctx)

def classify_spend(mandate, spend, history):
 vendor_lists = mandate.get('vendor_lists', {})
 rules = mandate.get('rules', [])
 for rule in rules:
  if rule.get('type') != RULE_REFLEX:
   continue
  name, operand = sole_predicate(rule.get('check'), 'rule %s check' % rule.get('id'))
  if not evaluate_predicate(name, operand, spend, history, vendor_lists):
   return (SPEND_REFUSED, [rule['id']])
 fired = []
 for rule in rules:
  if rule.get('type') != RULE_JUDGMENT:
   continue
  name, operand = sole_predicate(rule.get('when'), 'rule %s when' % rule.get('id'))
  if evaluate_predicate(name, operand, spend, history, vendor_lists):
   fired.append(rule['id'])
 if fired:
  return (SPEND_HELD, fired)
 return (SPEND_SETTLED, [])

def uncommitted_artifact(*, held_at, now, response_window_seconds):
 held_at = _require_int(held_at, 'held_at')
 now = _require_int(now, 'now')
 window = _require_int(response_window_seconds, 'response_window_seconds')
 if now < held_at:
  raise RemitError('now %d precedes held_at %d' % (now, held_at))
 return ARTIFACT_FORECLOSED if now - held_at < window else ARTIFACT_ABSENT

def _outcome_from_default(token, context):
 _require_one_of(token, DEFAULTS_VOCAB, context)
 return OUTCOME_REFUSED if token == DEFAULT_REFUND else OUTCOME_ALLOWED

def resolve_hold(*, verdict, artifact, requires_artifact, defaults, deadline_reached):
 _require_one_of(artifact, ARTIFACT_STATES, 'artifact state')
 for key in REQUIRED_DEFAULTS:
  if key not in defaults:
   raise RemitError('defaults: missing %r' % key)
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
 errors = []

 def bad(message):
  errors.append(message)
 if not isinstance(mandate, dict):
  return ['mandate: expected an object']
 version = mandate.get('version')
 if isinstance(version, bool) or not isinstance(version, int):
  bad('version: expected int')
 elif version <= stored_version:
  bad('version: %r does not exceed stored version %r' % (version, stored_version))
 defaults = mandate.get('defaults')
 if not isinstance(defaults, dict):
  bad('defaults: expected an object')
  defaults = {}
 for key in REQUIRED_DEFAULTS:
  if key not in defaults:
   bad('defaults: missing %r' % key)
 for key in ('on_deadline', 'on_undetermined'):
  if key in defaults and defaults[key] not in DEFAULTS_VOCAB:
   bad('defaults.%s: expected one of %s' % (key, list(DEFAULTS_VOCAB)))
 for key in ('response_window_seconds', 'hold_deadline_seconds', 'clawback_window_seconds'):
  if key in defaults:
   try:
    _require_int(defaults[key], 'defaults.' + key)
   except RemitError as exc:
    bad(str(exc))
 if 'response_window_seconds' in defaults and 'hold_deadline_seconds' in defaults:
  try:
   window = _require_int(defaults['response_window_seconds'], 'w')
   deadline = _require_int(defaults['hold_deadline_seconds'], 'd')
   if window >= deadline:
    bad('defaults: response_window_seconds must be less than hold_deadline_seconds')
  except RemitError:
   pass
 vendor_lists = mandate.get('vendor_lists', {})
 if not isinstance(vendor_lists, dict):
  bad('vendor_lists: expected an object')
  vendor_lists = {}
 for name in vendor_lists:
  if not isinstance(vendor_lists[name], (list, tuple)):
   bad('vendor_lists.%s: expected a list' % name)
   continue
  for addr in vendor_lists[name]:
   try:
    normalize_address(addr, 'vendor_lists.' + str(name))
   except RemitError as exc:
    bad(str(exc))
 rules = mandate.get('rules')
 if not isinstance(rules, (list, tuple)):
  return errors + ['rules: expected a list']
 seen = set()
 for index, rule in enumerate(rules):
  where = 'rules[%d]' % index
  if not isinstance(rule, dict):
   bad('%s: expected an object' % where)
   continue
  rule_id = rule.get('id')
  if not isinstance(rule_id, str) or rule_id == '':
   bad('%s.id: expected a non-empty string' % where)
  elif rule_id in seen:
   bad('%s.id: duplicate rule id %r' % (where, rule_id))
  else:
   seen.add(rule_id)
  rule_type = rule.get('type')
  if rule_type not in RULE_TYPES:
   bad('%s.type: expected one of %s' % (where, list(RULE_TYPES)))
   continue
  key = 'check' if rule_type == RULE_REFLEX else 'when'
  try:
   name, operand = sole_predicate(rule.get(key), '%s.%s' % (where, key))
   if name not in PREDICATES:
    bad('%s.%s: predicate %r is outside the v1 vocabulary' % (where, key, name))
   elif name in PREDICATES_INT:
    _require_int(operand, '%s.%s.%s' % (where, key, name))
   elif name in PREDICATES_WINDOW_AMOUNT:
    _window_operand(operand, 'amount', '%s.%s.%s' % (where, key, name))
   elif name in PREDICATES_WINDOW_COUNT:
    _window_operand(operand, 'count', '%s.%s.%s' % (where, key, name))
   elif name in PREDICATES_LIST_NAME:
    list_name = _require_str(operand, '%s.%s' % (where, key))
    if list_name not in vendor_lists:
     bad('%s.%s: vendor list %r is not defined' % (where, key, list_name))
   elif name in PREDICATES_STR_SET:
    if not isinstance(operand, (list, tuple)) or not operand:
     bad('%s.%s.%s: expected a non-empty list' % (where, key, name))
  except RemitError as exc:
   bad(str(exc))
  if rule_type == RULE_JUDGMENT:
   if not isinstance(rule.get('ask'), str) or not rule.get('ask'):
    bad('%s.ask: expected a non-empty string' % where)
   on_breach = rule.get('on_breach')
   if not isinstance(on_breach, dict) or 'tier' not in on_breach:
    bad("%s.on_breach: expected an object with 'tier'" % where)
   else:
    try:
     tier = _require_int(on_breach['tier'], '%s.on_breach.tier' % where)
     if tier > max_tier:
      bad('%s.on_breach.tier: %d exceeds registered max_tier %d' % (where, tier, max_tier))
    except RemitError as exc:
     bad(str(exc))
   if rule.get('requires_artifact') and (not isinstance(rule.get('requires_artifact'), bool)):
    bad('%s.requires_artifact: expected a bool' % where)
   has_uri = bool(rule.get('context_uri'))
   has_digest = bool(rule.get('context_digest'))
   if has_uri != has_digest:
    bad('%s: context_uri and context_digest must be given together' % where)
 return errors

def _rule_view(rule):
 kind = str(rule['type'])
 cond = rule['check'] if kind == RULE_REFLEX else rule['when']
 name, operand = sole_predicate(cond, 'rule ' + str(rule['id']))
 a, b, s = (0, 0, '')
 if name in PREDICATES_INT:
  a = int(operand)
 elif name in PREDICATES_WINDOW_AMOUNT:
  a, b = (int(operand['amount']), int(operand['seconds']))
 elif name in PREDICATES_WINDOW_COUNT:
  a, b = (int(operand['count']), int(operand['seconds']))
 elif name in PREDICATES_LIST_NAME:
  s = str(operand)
 else:
  s = ','.join([str(c) for c in operand])
 return {'id': str(rule['id']), 'type': kind, 'predicate': name, 'cond': {name: operand}, 'a': a, 'b': b, 's': s, 'requires_artifact': bool(rule.get('requires_artifact', False)), 'tier': int(rule.get('on_breach', {}).get('tier', 0)), 'ask': str(rule.get('ask', ''))}

def api_compile(mandate_json, max_tier):
 try:
  mandate = json.loads(mandate_json)
 except Exception:
  return json.dumps({'errors': ['mandate: not valid JSON']})
 errors = validate_mandate(mandate, stored_version=0, max_tier=int(max_tier))
 if errors:
  return json.dumps({'errors': errors})
 lists = {}
 for name in mandate.get('vendor_lists', {}):
  lists[str(name)] = [normalize_address(a) for a in mandate['vendor_lists'][name]]
 return json.dumps({'errors': [], 'mandate_version': int(mandate['version']), 'mandate_uri': str(mandate.get('mandate_uri', '')), 'mandate_digest': str(mandate.get('mandate_digest', '')).lower(), 'defaults': {k: mandate['defaults'][k] for k in REQUIRED_DEFAULTS}, 'vendor_lists': lists, 'rules': [_rule_view(r) for r in mandate['rules']]})

def _mandate_of(compiled):
 rules = []
 for r in compiled['rules']:
  rules.append({'id': r['id'], 'type': r['type'], 'check' if r['type'] == RULE_REFLEX else 'when': r['cond']})
 return {'rules': rules, 'vendor_lists': compiled['vendor_lists']}

def _spend_of(row):
 return Spend(amount=int(row[0]), recipient=str(row[1]), category=str(row[2]), at=int(row[3]))

def api_classify(compiled_json, history_json, candidate_json):
 compiled = json.loads(compiled_json)
 state, fired = classify_spend(_mandate_of(compiled), _spend_of(json.loads(candidate_json)), [_spend_of(h) for h in json.loads(history_json)])
 return json.dumps({'state': state, 'rules': [str(r) for r in fired]})

def api_outcomes(compiled_json, requires_artifact):
 compiled = json.loads(compiled_json)
 table = {}
 for verdict in VERDICTS:
  table[verdict] = {}
  for artifact in ARTIFACT_STATES:
   table[verdict][artifact] = resolve_hold(verdict=verdict, artifact=artifact, requires_artifact=bool(requires_artifact), defaults=compiled['defaults'], deadline_reached=False)
 table['deadline'] = {}
 for artifact in ARTIFACT_STATES:
  table['deadline'][artifact] = resolve_hold(verdict=None, artifact=artifact, requires_artifact=bool(requires_artifact), defaults=compiled['defaults'], deadline_reached=True)
 return json.dumps(table)

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
