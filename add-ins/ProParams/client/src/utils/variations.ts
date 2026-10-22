import type { ExportFormat } from '../types/types';
import { applyUnitToExpression } from './expressionUnits';

const SINGLE_QUOTED = /^'(?:''|[^'])*'$/;
const DOUBLE_QUOTED = /^"(?:\\.|[^"\\])*"$/;
const TEXT_FORMULA = /[+;()]|==|!=|<=|>=|&&|\|\|/;
const ILLEGAL_FILENAME = /[<>:"/\\|?*\u0000-\u001f]/g;

function normalizeTextQuotes(value: string): string {
  return value.replace(/[\u201c\u201d]/g, '"').replace(/[\u2018\u2019]/g, "'");
}

/** Fusion text literal. Plain text and double quotes become single quotes. Formulas stay as written. */
export function textExpression(value: string): string {
  const trimmed = normalizeTextQuotes(value.trim());
  if (!trimmed) return "''";
  if (SINGLE_QUOTED.test(trimmed)) return trimmed;
  if (DOUBLE_QUOTED.test(trimmed)) {
    const plain = trimmed.slice(1, -1).replace(/\\\\/g, '\\').replace(/\\"/g, '"');
    return `'${plain.replace(/'/g, "''")}'`;
  }
  if (TEXT_FORMULA.test(trimmed)) return trimmed;
  return `'${trimmed.replace(/'/g, "''")}'`;
}

/** Characters inside a text literal. Formulas are returned as written. */
export function textDisplay(expression: string): string {
  const trimmed = normalizeTextQuotes(expression.trim());
  if (SINGLE_QUOTED.test(trimmed)) return trimmed.slice(1, -1).replace(/''/g, "'");
  if (DOUBLE_QUOTED.test(trimmed)) return trimmed.slice(1, -1).replace(/\\\\/g, '\\').replace(/\\"/g, '"');
  return expression;
}

function withoutLeadingEquals(expression: string): string {
  const text = expression.trim();
  if (text.startsWith('=') && !text.startsWith('==')) return text.slice(1).trim();
  return text;
}

/** Value stored on the parameter. Text is quoted. A bare number picks up `unit`. */
export function prepareVariationValue(value: string, unit: string): string {
  const trimmed = withoutLeadingEquals(value);
  if (!trimmed) return '';
  if (unit === 'Text') return textExpression(trimmed);
  return applyUnitToExpression(trimmed, unit);
}

/** Editor text for a stored variation. Text parameters show the characters, not the quotes. */
export function variationEditorValue(value: string, unit: string): string {
  if (unit === 'Text') return textDisplay(value);
  return value;
}

/** File count for the cartesian product. Empty lists do not take part. */
export function variationFileCount(lengths: number[]): number {
  const active = lengths.filter((length) => length > 0);
  if (active.length === 0) return 0;
  return active.reduce((count, length) => count * length, 1);
}

export type VariationPart = { name: string; value: string };

/** One entry per combination, in list order. Parameters with no values are skipped. */
export function cartesianVariations(params: { name: string; values: string[] }[]): VariationPart[][] {
  const active = params.filter((param) => param.values.length > 0);
  if (active.length === 0) return [];
  let combos: VariationPart[][] = [[]];
  for (const param of active) {
    combos = combos.flatMap((combo) => param.values.map((value) => [...combo, { name: param.name, value }]));
  }
  return combos;
}

export function filenameToken(text: string): string {
  const cleaned = text.replace(ILLEGAL_FILENAME, '').replace(/\s+/g, ' ').trim().replace(/^[. ]+|[. ]+$/g, '');
  return cleaned || 'value';
}

export function variationFileName(documentName: string, combo: VariationPart[], format: ExportFormat): string {
  const doc = filenameToken(documentName.trim() || 'Design');
  const body = combo
    .map((part) => `${filenameToken(part.name)}-${filenameToken(textDisplay(part.value))}`)
    .join('__');
  return `${doc}__${body}.${format}`;
}
