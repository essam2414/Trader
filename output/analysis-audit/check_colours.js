async page => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const colours = {};
  for (const id of ["rsi14", "rs5", "atr14"]) {
    colours[id] = await page.getByTestId("metric-" + id).evaluate(node => getComputedStyle(node).color);
  }
  if (colours.rsi14 !== "rgb(50, 230, 77)" || colours.rs5 !== "rgb(255, 75, 85)" || colours.atr14 !== "rgb(255, 255, 255)") {
    throw new Error(JSON.stringify(colours));
  }
  await page.screenshot({ path: "output/playwright/stock-analysis-audited.png", fullPage: true });
  return colours;
}
