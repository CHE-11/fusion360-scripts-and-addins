import { FUSION_UNITS } from '../data/fusionUnits';

/**
 * Guess a parameter unit from an expression, and keep a plain value valid
 * when the user picks a unit.
 *
 * `5"`, `5 in`, and `5 mm` map to the matching Fusion unit. A value with no
 * unit token stays unitless until the user picks one. Picking `mm` for `5`
 * rewrites the expression to `5 mm`.
 */

type Alias = {
  token: string;
  symbol: string;
  caseSensitive: boolean;
};

const SKIP_KEYWORDS = new Set([
  'none',
  'number',
  'string',
  'angle',
  'current',
  'voltage',
  'resistance',
  'charge',
  'capacitance',
  'conductance',
  'inductance',
  'substance',
  'viscosity',
  'piece',
  'count',
  'each',
  'currency',
  'ul',
]);

const EXTRA_ALIASES: { token: string; symbol: string }[] = [
  { token: '"', symbol: 'in' },
  { token: '″', symbol: 'in' },
  { token: '“', symbol: 'in' },
  { token: '”', symbol: 'in' },
  { token: "'", symbol: 'ft' },
  { token: '′', symbol: 'ft' },
  { token: '‘', symbol: 'ft' },
  { token: '’', symbol: 'ft' },
  { token: '°', symbol: 'deg' },
  { token: 'inch', symbol: 'in' },
  { token: 'degree', symbol: 'deg' },
];

const NUMBER_RE = /(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/g;
const SIMPLE_NUMBER_RE = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/;

function buildAliases(): Alias[] {
  const raw: { token: string; symbol: string }[] = [];
  for (const unit of FUSION_UNITS) {
    if (!unit.symbol || unit.symbol === 'Text') continue;
    raw.push({ token: unit.symbol, symbol: unit.symbol });
    for (const keyword of unit.keywords ?? []) {
      if (SKIP_KEYWORDS.has(keyword.toLowerCase())) continue;
      raw.push({ token: keyword, symbol: unit.symbol });
    }
  }
  raw.push(...EXTRA_ALIASES);

  const symbolsByFold = new Map<string, Set<string>>();
  for (const entry of raw) {
    const fold = entry.token.toLowerCase();
    const symbols = symbolsByFold.get(fold) ?? new Set<string>();
    symbols.add(entry.symbol);
    symbolsByFold.set(fold, symbols);
  }

  const aliases: Alias[] = [];
  const seen = new Set<string>();
  for (const entry of raw) {
    const caseSensitive = (symbolsByFold.get(entry.token.toLowerCase())?.size ?? 0) > 1;
    const key = `${caseSensitive ? entry.token : entry.token.toLowerCase()}\0${entry.symbol}`;
    if (seen.has(key)) continue;
    seen.add(key);
    aliases.push({ token: entry.token, symbol: entry.symbol, caseSensitive });
  }
  aliases.sort((a, b) => b.token.length - a.token.length || a.token.localeCompare(b.token));
  return aliases;
}

const ALIASES = buildAliases();

function isValueBoundary(prev: string | undefined): boolean {
  if (!prev) return true;
  return !/[A-Za-z0-9_.]/.test(prev);
}

/** Longest unit token at the start of `text`, ignoring leading spaces. */
function matchUnitAt(text: string): { symbol: string; consumed: number } | null {
  const whitespace = text.match(/^[ \t]*/)?.[0].length ?? 0;
  const rest = text.slice(whitespace);
  for (const alias of ALIASES) {
    if (rest.length < alias.token.length) continue;
    const slice = rest.slice(0, alias.token.length);
    const equal = alias.caseSensitive
      ? slice === alias.token
      : slice.toLowerCase() === alias.token.toLowerCase();
    if (!equal) continue;
    const next = rest[alias.token.length];
    if (next !== undefined && /[A-Za-z0-9_^]/.test(next)) continue;
    return { symbol: alias.symbol, consumed: whitespace + alias.token.length };
  }
  return null;
}

/**
 * Unit written on a number in the expression (`5 mm`, `5"`, `2 * 5 in`).
 * The last one wins. Returns undefined when the expression is unitless.
 */
export function guessUnitFromExpression(expression: string): string | undefined {
  NUMBER_RE.lastIndex = 0;
  let found: string | undefined;
  let match: RegExpExecArray | null;
  while ((match = NUMBER_RE.exec(expression))) {
    if (!isValueBoundary(expression[match.index - 1])) continue;
    const unit = matchUnitAt(expression.slice(match.index + match[0].length));
    if (unit) found = unit.symbol;
  }
  return found;
}

type SimpleValue = {
  number: string;
  /** Fusion symbol for a trailing unit token, or null when the value is bare. */
  symbol: string | null;
};

/** A single numeric literal, optionally followed by one unit token. */
function parseSimpleValue(expression: string): SimpleValue | null {
  const trimmed = expression.trim();
  const number = trimmed.match(SIMPLE_NUMBER_RE);
  if (!number) return null;
  const rest = trimmed.slice(number[0].length);
  if (rest.trim() === '') return { number: number[0], symbol: null };
  const unit = matchUnitAt(rest);
  if (!unit) return null;
  if (rest.slice(unit.consumed).trim() !== '') return null;
  return { number: number[0], symbol: unit.symbol };
}

/**
 * Rewrite a plain value so it carries `unit`.
 * Formulas are left alone. Unitless clears a trailing unit on a plain value.
 * `Text` is not an expression suffix.
 */
export function applyUnitToExpression(expression: string, unit: string): string {
  const parsed = parseSimpleValue(expression);
  if (!parsed) return expression;
  if (!unit || unit === 'Text') {
    if (!parsed.symbol) return expression;
    return parsed.number;
  }
  if (parsed.symbol === unit) return expression;
  return `${parsed.number} ${unit}`;
}

export function syncExpressionUnit(
  expression: string,
  unit: string,
  source: 'expression' | 'unit'
): { expression: string; unit: string } {
  if (source === 'unit') {
    return { expression: applyUnitToExpression(expression, unit), unit };
  }
  const guessed = guessUnitFromExpression(expression);
  if (guessed) return { expression, unit: guessed };
  return { expression: applyUnitToExpression(expression, unit), unit };
}
