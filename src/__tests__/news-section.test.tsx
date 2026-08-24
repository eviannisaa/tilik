/**
 * The local-news section.
 *
 * The payloads are real: captured from `/api/location/news` for Surabaya and
 * Tangerang Selatan. The section's job is to stay honest — it reports what was
 * *published about an area*, which is a weaker claim than the measured and
 * modelled sections around it, and the UI has to say so.
 */

import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import NewsSection from "../components/report/NewsSection";
import type { LocalNews, NewsItem } from "../lib/types";

const item = (over: Partial<NewsItem> & { id: string; title: string }): NewsItem => ({
  url: `https://news.google.com/rss/articles/${over.id}`,
  publishedAt: "2026-08-02T07:00:00+00:00",
  source: "detikNews",
  topic: "wildfire",
  topicLabel: "Forest & land fire",
  ...over,
});

const SURABAYA: LocalNews = {
  matchedArea: "Surabaya",
  monthsSearched: 12,
  status: "ok",
  topics: ["wildfire", "flood"],
  note: null,
  items: [
    item({ id: "a", title: "Kebakaran Rumah di Simo Gunung Surabaya" }),
    item({ id: "b", title: "Kebakaran Toko Sembako di Putat Jaya Surabaya" }),
    item({ id: "c", title: "Kebakaran di Apartemen Tengah Kota Surabaya" }),
    item({ id: "d", title: "Kebakaran Mobil Listrik di Apartemen Surabaya" }),
    item({
      id: "e",
      title: "Ancaman Banjir Rob Mengintai Pesisir Surabaya",
      topic: "flood",
      topicLabel: "Flood",
      publishedAt: "2026-07-27T07:00:00+00:00",
    }),
    item({
      id: "f",
      title: "Soal Banjir Rob di Surabaya, Pakar Unair Ingatkan Masalah Lama",
      topic: "flood",
      topicLabel: "Flood",
      publishedAt: "2026-07-23T07:00:00+00:00",
    }),
  ],
};

const empty = (over: Partial<LocalNews>): LocalNews => ({
  items: [],
  matchedArea: null,
  monthsSearched: 12,
  status: "no_results",
  topics: [],
  note: null,
  ...over,
});

afterEach(cleanup);

describe("local news", () => {
  it("names the area it actually searched", () => {
    render(() => <NewsSection index={5} news={SURABAYA} />);

    // The results are only as precise as the place name behind them, so the
    // name is part of the finding, not a footnote.
    const summary = screen.getByText(/stories from the last/i);
    expect(summary.textContent).toContain("6 stories from the last 12 months");
    expect(summary.textContent).toContain("naming Surabaya");
  });

  it("says the match is by place name, not by point", () => {
    render(() => <NewsSection index={5} news={SURABAYA} />);
    expect(screen.getByText(/may be about somewhere else in the same area/i)).toBeTruthy();
  });

  it("filters to one topic and back", () => {
    render(() => <NewsSection index={5} news={SURABAYA} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);

    fireEvent.click(screen.getByRole("button", { name: "Flood 2" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    // Clicking the active chip clears it rather than trapping the reader.
    fireEvent.click(screen.getByRole("button", { name: "Flood 2" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("marks the active filter for assistive tech", () => {
    render(() => <NewsSection index={5} news={SURABAYA} />);
    const flood = screen.getByRole("button", { name: "Flood 2" });

    expect(screen.getByRole("button", { name: "All 6" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(flood);
    expect(flood.getAttribute("aria-pressed")).toBe("true");
  });

  it("holds long lists back behind one control", () => {
    render(() => <NewsSection index={5} news={SURABAYA} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);

    fireEvent.click(screen.getByRole("button", { name: /show all 6 stories/i }));
    expect(screen.getAllByRole("listitem")).toHaveLength(6);
  });

  it("opens stories in a new tab without leaking the referrer", () => {
    render(() => <NewsSection index={5} news={SURABAYA} />);
    const link = screen.getAllByRole("link")[0]!;

    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("distinguishes nothing-reported from nothing-searched", () => {
    render(() => <NewsSection index={5} news={empty({ status: "no_results" })} />);
    expect(screen.getByText(/nothing reported in this window/i)).toBeTruthy();

    // Quiet coverage is not an all-clear, and the section must not imply one.
    expect(screen.getByText(/not the same as a quiet place/i)).toBeTruthy();
  });

  it("explains an unnamed area rather than showing an empty list", () => {
    render(() => <NewsSection index={5} news={empty({ status: "no_area" })} />);
    expect(screen.getByText(/couldn't name this area/i)).toBeTruthy();
  });

  it("says a feed failure costs only this section", () => {
    render(() => <NewsSection index={5} news={empty({ status: "unavailable" })} />);
    expect(screen.getByText(/didn't answer/i)).toBeTruthy();
    expect(screen.getByText(/every other section of this report is unaffected/i)).toBeTruthy();
  });

  it("prefers the provider's own note over the generic copy", () => {
    render(() =>
      <NewsSection index={5} news={empty({ status: "no_results", note: "No hazard reporting for Surabaya in the last 12 months." })} />
    );
    expect(screen.getByText(/no hazard reporting for surabaya/i)).toBeTruthy();
  });

  it("hides the filter row when there is only one topic", () => {
    const single = { ...SURABAYA, items: SURABAYA.items.slice(0, 2) };
    render(() => <NewsSection index={5} news={single} />);
    expect(screen.queryByRole("group", { name: /filter news by topic/i })).toBeNull();
  });
});
