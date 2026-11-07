// Preserve Java BigDecimal/BigInteger JSON tokens without passing through IEEE-754.
// No scoring is performed here. Numeric values are opaque decimal lexemes.
const numberPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;
export class Decimal {
  constructor(text) {
    if (typeof text !== 'string' || !numberPattern.test(text)) throw new Error('Некорректное JSON-число. Используйте точку, без разделителей тысяч.');
    this.text = text; Object.freeze(this);
  }
  toString() { return this.text; }
}
export const decimal = value => new Decimal(String(value));
export const display = value => value === null || value === undefined ? 'N/A' : String(value);
export function integer(value, minimum = 1n) {
  const text = String(value);
  if (!/^(0|[1-9]\d*)$/.test(text) || BigInt(text) < minimum) throw new Error('Версия должна быть целым числом в допустимом диапазоне.');
  return text;
}
export function parse(text) {
  let at = 0;
  const fail = () => { throw new Error('Некорректный JSON.'); };
  const space = () => { while (/[\x20\t\r\n]/.test(text[at] || 'x')) at++; };
  function string() {
    const start = at++;
    while (at < text.length) {
      const c = text[at++];
      if (c === '\\') { at++; continue; }
      if (c === '"') return JSON.parse(text.slice(start, at));
    }
    return fail();
  }
  function value(depth = 0) {
    if (depth > 100) return fail();
    space(); const c = text[at];
    if (c === '"') return string();
    if (c === '[' || c === '{') {
      at++; const array = c === '['; const result = array ? [] : Object.create(null);
      const end = array ? ']' : '}'; space();
      if (text[at] === end) { at++; return result; }
      while (at < text.length) {
        space();
        if (array) result.push(value(depth + 1));
        else {
          if (text[at] !== '"') return fail();
          const key = string(); space();
          if (text[at++] !== ':' || Object.hasOwn(result, key)) return fail();
          result[key] = value(depth + 1);
        }
        space(); const next = text[at++];
        if (next === end) return result;
        if (next !== ',') return fail();
      }
      return fail();
    }
    for (const [token, result] of [['true', true], ['false', false], ['null', null]]) {
      if (text.startsWith(token, at)) { at += token.length; return result; }
    }
    const match = text.slice(at).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
    if (!match) return fail();
    at += match[0].length; return decimal(match[0]);
  }
  const result = value(); space(); if (at !== text.length) fail(); return result;
}
export function stringify(value) {
  if (value instanceof Decimal) return value.text;
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('Нельзя отправить число с потерей точности.');
    return String(value);
  }
  if (Array.isArray(value)) return '[' + value.map(stringify).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.entries(value).map(([k,v]) => JSON.stringify(k) + ':' + stringify(v)).join(',') + '}';
  throw new Error('Неподдерживаемое JSON-значение.');
}
export const clone = value => parse(stringify(value));
// Numeric equivalence for selecting an existing discrete level (7 == 7.0), not scoring.
export function equalDecimal(a, b) {
  if (a === null || b === null) return a === b;
  function canonical(value) {
    const text = String(value); if (!numberPattern.test(text)) throw new Error('Некорректное число.');
    const [mantissa, exp = '0'] = text.toLowerCase().split('e');
    const sign = mantissa.startsWith('-') ? '-' : '';
    const unsigned = mantissa.replace(/^-/, '');
    const fraction = unsigned.split('.')[1]?.length ?? 0;
    let digits = unsigned.replace('.', '').replace(/^0+/, '');
    if (!digits) return '0';
    const trailing = digits.match(/0*$/)[0].length;
    digits = digits.slice(0, digits.length - trailing);
    return sign + digits + 'e' + (BigInt(exp) - BigInt(fraction) + BigInt(trailing));
  }
  return canonical(a) === canonical(b);
}
