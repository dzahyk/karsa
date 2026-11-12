import { describe, expect, it } from "vitest";
import { idr, parseWhole, pct, relative, valueDisplay } from "./format";

describe("format", () => {
  it("formats whole rupiah", () => {
    expect(idr(150_000_000)).toBe("Rp150,000,000");
    expect(idr(-2_000_000)).toBe("−Rp2,000,000");
    expect(idr(null)).toBe("—");
  });
  it("formats basis points without float drift", () => {
    expect(pct(2200)).toBe("22.00%");
    expect(pct(2167)).toBe("21.67%");
    expect(pct(-250)).toBe("−2.50%");
  });
  it("parses typed amounts strictly", () => {
    expect(parseWhole("Rp150.000.000")).toBe(150_000_000);
    expect(parseWhole("3,000")).toBe(3000);
    expect(parseWhole("12.5k")).toBeNull();
    expect(parseWhole("")).toBeNull();
  });
  it("renders requirement values by type", () => {
    expect(valueDisplay("weeks", "8")).toBe("8 weeks");
    expect(valueDisplay("integer", "3000")).toBe("3,000");
    expect(valueDisplay("text", null)).toBe("—");
  });
  it("describes relative time", () => {
    const now = Date.parse("2026-11-11T10:00:00Z");
    expect(relative("2026-11-11T08:00:00Z", now)).toBe("2 hours ago");
  });
});
