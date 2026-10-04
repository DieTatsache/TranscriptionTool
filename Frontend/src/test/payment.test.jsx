import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import MockPayment from "../components/MockPayment.jsx";
import { TEST_CARDS, cardProblem, formatCardNumber, formatExpiry, tokenize } from "../mockPaymentProvider.js";

const PRO = { id: "pro", name: "Pro", monthly_price_cents: 9900 };
const NOW = new Date(2026, 9, 4); // 4 Oct 2026

function fill(label, value) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function enterCard({ name = "Ada Lovelace", card = "4242 4242 4242 4242", expiry = "12/40", cvc = "123" } = {}) {
  fill("Cardholder name", name);
  fill("Card number", card);
  fill("Expiry", expiry);
  fill("CVC", cvc);
  fireEvent.click(screen.getByRole("button", { name: /^Pay €99/ }));
}

describe("mock payment provider (browser side)", () => {
  const valid = { card: "4242 4242 4242 4242", expiry: "10/26", cvc: "123", name: "Ada" };

  it("accepts only the documented test cards", () => {
    expect(cardProblem(valid, NOW)).toBeNull();
    expect(cardProblem({ ...valid, card: "4111 1111 1111 1111" }, NOW)).toMatch(/Never enter a real card/);
    expect(TEST_CARDS.map((c) => tokenize(c.number))).toEqual([
      "tok_visa",
      "tok_mastercard",
      "tok_chargeDeclined",
      "tok_chargeDeclinedInsufficientFunds",
    ]);
    expect(tokenize("4111111111111111")).toBeNull();
  });

  it.each([
    [{ name: "  " }, /cardholder name/],
    [{ expiry: "09/26" }, /expiry/], // last month
    [{ expiry: "13/30" }, /expiry/],
    [{ expiry: "1/30" }, /expiry/],
    [{ expiry: "" }, /expiry/],
    [{ cvc: "12" }, /CVC/],
    [{ cvc: "12a" }, /CVC/],
  ])("rejects %o", (change, problem) => {
    expect(cardProblem({ ...valid, ...change }, NOW)).toMatch(problem);
  });

  it("formats what is typed", () => {
    expect(formatCardNumber("4242-4242 4242x4242 99")).toBe("4242 4242 4242 4242");
    expect(formatExpiry("1240")).toBe("12/40");
    expect(formatExpiry("1")).toBe("1");
  });
});

describe("MockPayment", () => {
  it("sends only the provider token and shows the server's plan price", async () => {
    const checkout = vi.spyOn(api, "checkout").mockResolvedValue({ user: { plan: "pro" } });
    const onSuccess = vi.fn();
    render(<MockPayment plan={PRO} onSuccess={onSuccess} onCancel={vi.fn()} />);

    expect(screen.getAllByText("€99").length).toBeGreaterThan(0);
    enterCard({ card: "5555 5555 5555 4444" });

    expect(await screen.findByText("Payment confirmed")).toBeTruthy();
    expect(checkout).toHaveBeenCalledExactlyOnceWith("pro", "tok_mastercard");
    expect(JSON.stringify(checkout.mock.calls)).not.toContain("5555");
    fireEvent.click(screen.getByRole("button", { name: /Go to my account/ }));
    expect(onSuccess).toHaveBeenCalledWith({ plan: "pro" });
  });

  it("refuses unknown cards without contacting the server", () => {
    const checkout = vi.spyOn(api, "checkout");
    render(<MockPayment plan={PRO} onSuccess={vi.fn()} onCancel={vi.fn()} />);
    enterCard({ card: "4111 1111 1111 1111" });
    expect(screen.getByRole("alert").textContent).toMatch(/Never enter a real card/);
    expect(checkout).not.toHaveBeenCalled();
  });

  it("keeps browsers from autofilling saved cards", () => {
    render(<MockPayment plan={PRO} onSuccess={vi.fn()} onCancel={vi.fn()} />);
    for (const label of ["Cardholder name", "Card number", "Expiry", "CVC"]) {
      expect(screen.getByLabelText(label).getAttribute("autocomplete")).toBe("off");
    }
  });

  it("shows a decline and lets the user try again with emptied card fields", async () => {
    const declined = Object.assign(new Error("Your card was declined."), { code: "payment_declined" });
    const checkout = vi
      .spyOn(api, "checkout")
      .mockRejectedValueOnce(declined)
      .mockResolvedValueOnce({ user: { plan: "pro" } });
    render(<MockPayment plan={PRO} onSuccess={vi.fn()} onCancel={vi.fn()} />);

    enterCard({ card: "4000 0000 0000 0002" });

    expect((await screen.findByRole("alert")).textContent).toBe("Your card was declined.");
    expect(screen.getByLabelText("Card number").value).toBe(""); // card data isn't kept
    expect(screen.getByLabelText("CVC").value).toBe("");
    expect(checkout).toHaveBeenCalledWith("pro", "tok_chargeDeclined");
    enterCard();
    expect(await screen.findByText("Payment confirmed")).toBeTruthy();
  });

  it("hides technical errors behind a generic message", async () => {
    vi.spyOn(api, "checkout").mockRejectedValue(Object.assign(new Error("boom"), { code: "error" }));
    render(<MockPayment plan={PRO} onSuccess={vi.fn()} onCancel={vi.fn()} />);
    enterCard();
    expect((await screen.findByRole("alert")).textContent).toBe(
      "The payment could not be completed. Please try again.",
    );
  });

  it("treats a plan that is already active as done", async () => {
    vi.spyOn(api, "checkout").mockRejectedValue(Object.assign(new Error("x"), { code: "already_on_plan" }));
    const onSuccess = vi.fn();
    render(<MockPayment plan={PRO} onSuccess={onSuccess} onCancel={vi.fn()} />);
    enterCard();
    await vi.waitFor(() => expect(onSuccess).toHaveBeenCalledWith(null));
  });

  it("test cards can be picked from the list and the dialog closed", () => {
    const onCancel = vi.fn();
    render(<MockPayment plan={PRO} onSuccess={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "4000 0000 0000 9995" }));
    expect(screen.getByLabelText("Card number").value).toBe("4000 0000 0000 9995");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
