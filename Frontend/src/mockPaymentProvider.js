// Stand-in for a payment provider's browser SDK (like Stripe.js): card details are checked
// and turned into a one-time token here, in the browser; only the token goes to the API.
// It knows nothing but the provider's documented test cards, so a real card is refused
// before it could go anywhere.

export const TEST_CARDS = [
  { number: "4242424242424242", token: "tok_visa", label: "Visa · succeeds" },
  { number: "5555555555554444", token: "tok_mastercard", label: "Mastercard · succeeds" },
  { number: "4000000000000002", token: "tok_chargeDeclined", label: "Declined" },
  { number: "4000000000009995", token: "tok_chargeDeclinedInsufficientFunds", label: "Insufficient funds" },
];

function digits(value) {
  return value.replace(/\D/g, "");
}

export function formatCardNumber(value) {
  return digits(value).slice(0, 16).replace(/(.{4})/g, "$1 ").trim();
}

export function formatExpiry(value) {
  const numbers = digits(value).slice(0, 4);
  return numbers.length > 2 ? `${numbers.slice(0, 2)}/${numbers.slice(2)}` : numbers;
}

function expired(month, year, now) {
  return new Date(2000 + year, month, 0, 23, 59, 59) < now; // last day of the month
}

// Returns a user-facing problem with the entered card, or null.
export function cardProblem({ card, expiry, cvc, name }, now = new Date()) {
  if (!name.trim()) return "Please enter the cardholder name.";
  if (!TEST_CARDS.some((c) => c.number === digits(card))) {
    return "This is a simulated checkout: please use one of the test cards below. Never enter a real card.";
  }
  const [month, year] = expiry.split("/").map((part) => (/^\d{2}$/.test(part) ? Number(part) : NaN));
  if (!(month >= 1 && month <= 12) || Number.isNaN(year) || expired(month, year, now)) {
    return "Please enter a valid expiry date in the future.";
  }
  if (!/^\d{3,4}$/.test(cvc)) return "Please enter a valid CVC.";
  return null;
}

export function tokenize(card) {
  return TEST_CARDS.find((c) => c.number === digits(card))?.token ?? null;
}
