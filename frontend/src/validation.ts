// Turns the server's validation errors (FastAPI/Pydantic) into German messages that name the field.

const FIELD: Record<string, string> = {
  name: 'Bezeichnung',
  purpose: 'Art',
  principal: 'Darlehensbetrag',
  annual_rate_percent: 'Sollzins',
  monthly_payment: 'Monatliche Rate',
  initial_repayment_percent: 'Anfangstilgung',
  start: 'Beginn',
  contract_sum: 'Bausparsumme',
  monthly_saving: 'Sparbeitrag',
  allocation: 'Zuteilung',
  fee_percent: 'Abschlussgebühr (Prozent)',
  fee_amount: 'Abschlussgebühr (Euro)',
  deposit_rate_percent: 'Guthabenzins',
  loan_rate_percent: 'Darlehenszins',
  loan_payment: 'Rate in der Darlehensphase',
  limit: 'Rahmen',
  balance: 'Aktuell genutzt',
  reason: 'Begründung',
  value: 'Wert',
  month: 'Monat',
  amount: 'Betrag',
  email: 'E-Mail',
  password: 'Passwort',
  display_name: 'Name',
  household_name: 'Haushaltsname',
  invite_code: 'Einladungscode',
  isin: 'ISIN',
}

interface Issue {
  type?: string
  loc?: (string | number)[]
  msg?: string
  ctx?: Record<string, unknown>
}

function describe(issue: Issue): string {
  const ctx = issue.ctx ?? {}
  const num = (v: unknown) => String(v).replace('.', ',')
  switch (issue.type) {
    case 'less_than_equal':
      return `darf höchstens ${num(ctx.le)} sein`
    case 'less_than':
      return `muss kleiner als ${num(ctx.lt)} sein`
    case 'greater_than':
      return ctx.gt === 0 || ctx.gt === '0' ? 'muss größer als 0 sein' : `muss größer als ${num(ctx.gt)} sein`
    case 'greater_than_equal':
      return `muss mindestens ${num(ctx.ge)} sein`
    case 'missing':
      return 'fehlt'
    case 'string_too_short':
      return ctx.min_length === 1 ? 'darf nicht leer sein' : `braucht mindestens ${String(ctx.min_length)} Zeichen`
    case 'string_too_long':
      return `darf höchstens ${String(ctx.max_length)} Zeichen haben`
    case 'decimal_parsing':
    case 'decimal_type':
    case 'int_parsing':
      return 'ist keine gültige Zahl'
    case 'decimal_max_places':
      return `darf höchstens ${String(ctx.decimal_places)} Nachkommastellen haben`
    case 'decimal_max_digits':
    case 'decimal_whole_digits':
      return 'ist zu groß'
    case 'value_error':
      return (issue.msg ?? '').replace(/^Value error, /, '')
    default:
      return issue.msg ?? 'ist ungültig'
  }
}

/** One readable sentence per problem, e.g. "Abschlussgebühr (Prozent): darf höchstens 5 sein." */
export function validationMessage(detail: Issue[]): string {
  return detail
    .map((issue) => {
      const field = [...(issue.loc ?? [])].reverse().find((p) => typeof p === 'string' && p !== 'body')
      const text = describe(issue)
      const label = typeof field === 'string' ? FIELD[field] : undefined
      // model-level errors are already full sentences and belong to no single field
      if (issue.type === 'value_error' && !label) return text
      const known = label ?? (typeof field === 'string' ? field : null)
      return known ? `${known}: ${text}.` : `${text}.`
    })
    .join(' ')
}
