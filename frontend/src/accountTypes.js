// The account types offered when opening an account. The English string is what is stored and sent to the API
// (which accepts any non-empty string up to 50 characters); only its label is translated.
export const ACCOUNT_TYPES = ['Checking', 'Savings', 'Current', 'Business', 'Student'];

// Translated label for a known type; any other (legacy or unknown) stored value is shown as it is.
export const accountTypeLabel = (t, value) => ACCOUNT_TYPES.includes(value) ? t(`accounts.types.${value}`) : value;
