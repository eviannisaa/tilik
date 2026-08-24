/**
 * The evidence is behind a dialog now, so the trigger and the ways out are the
 * whole path to them — a regression here strands the report with no way in.
 *
 * jsdom implements `<dialog>` but not `showModal()`, so these exercise the
 * component's attribute fallback rather than the top layer. What that still
 * covers is the wiring: the store flag, the `close` event Escape fires, the
 * backdrop-click test, and the scroll lock. The top layer itself is the
 * browser's to get right.
 */

import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";
import AssessmentSummary from "../components/report/AssessmentSummary";
import Dialog from "../components/ui/Dialog";
import { displayStore } from "../lib/store";
import type { Assessment } from "../lib/types";

const assessment = {
  level: "moderate",
  headline: "Sits low, with flood exposure worth checking on the ground.",
  confidence: "high",
  disclaimer: "Not a substitute for a site survey.",
  factors: [{ label: "Flood risk", detail: "InaRISK 0.78 here.", impact: "negative" }],
} as unknown as Assessment;

afterEach(() => {
  cleanup();
  displayStore.closeReport();
});

describe("the way into the evidence", () => {
  it("offers the report from the foot of the verdict", () => {
    render(() => <AssessmentSummary assessment={assessment} />);

    expect(displayStore.reportOpen()).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /show the result/i }));
    expect(displayStore.reportOpen()).toBe(true);
  });

  it("keeps the trigger out of the scrolling factor list", () => {
    const { container } = render(() => <AssessmentSummary assessment={assessment} />);
    const button = screen.getByRole("button", { name: /show the result/i });

    // Inside the scroll box it would scroll away with the factors, which is the
    // one place the way out of the block must not be.
    expect(container.querySelector(".overflow-y-auto")?.contains(button)).toBe(false);
  });
});

describe("report dialog", () => {
  function open() {
    const [isOpen, setOpen] = createSignal(false);
    const onClose = vi.fn(() => setOpen(false));
    const { container } = render(() => (
      <Dialog open={isOpen()} onClose={onClose} label="The evidence behind this verdict">
        <p>the evidence</p>
      </Dialog>
    ));

    setOpen(true);
    return { dialog: container.querySelector("dialog")!, onClose, setOpen };
  }

  it("stays hidden when closed, whatever layout it needs when open", () => {
    const { container } = render(() => (
      <Dialog open={false} onClose={() => {}} label="The evidence behind this verdict">
        <p>the evidence</p>
      </Dialog>
    ));
    const dialog = container.querySelector("dialog")!;

    expect(dialog.hasAttribute("open")).toBe(false);
    expect(getComputedStyle(dialog).display).toBe("none");

    // The regression this exists for: a bare `flex` on the element sets `display`
    // from the author stylesheet, and author styles beat the UA stylesheet
    // whatever the specificity. That overrides `dialog:not([open])`'s
    // `display: none`, and the closed dialog renders inline in the page — the
    // whole report appearing under the map the moment a check finishes, with no
    // way to dismiss it. jsdom loads no CSS, so only the class list can catch it.
    const DISPLAY = [
      "block",
      "flex",
      "grid",
      "inline",
      "inline-flex",
      "inline-block",
      "table",
      "contents",
      "flow-root",
    ];
    const unconditional = dialog.className.split(/\s+/).filter((name) => DISPLAY.includes(name));

    expect(unconditional).toEqual([]);
    // Any display it needs must be scoped to the open state.
    expect(dialog.className).toContain("open:flex");
  });

  it("names itself and locks the page behind it", () => {
    const { dialog } = open();

    expect(dialog.open).toBe(true);
    expect(dialog.getAttribute("aria-label")).toBe("The evidence behind this verdict");
    // A backdrop that slides while the page scrolls under it reads as a fault.
    expect(document.documentElement.style.overflow).toBe("hidden");
  });

  it("closes on the backdrop, on the button, and on the browser's own close", () => {
    const { dialog, onClose, setOpen } = open();

    // A click whose target is the dialog itself landed on the backdrop; every
    // click on the content hits a child instead.
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(document.documentElement.style.overflow).toBe("");

    setOpen(true);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(2);

    // Escape closes the dialog without passing through the setter, so the flag
    // has to learn about it from the element.
    setOpen(true);
    dialog.dispatchEvent(new Event("close"));
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
