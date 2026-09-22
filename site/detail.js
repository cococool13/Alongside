const id = new URLSearchParams(location.search).get("id");
fetch("/pilots.json").then((r) => r.json()).then((data) => {
  const pilot = data.pilots.find((row) => row.id === id);
  if (!pilot) return;
  document.title = pilot.name;
  document.querySelector("#name").textContent = pilot.name;
  document.querySelector("#who").textContent = pilot.who;
  if (typeof pilot.return_90d === "number") {
    const ret = document.querySelector("#ret");
    ret.className = "chip";
    ret.textContent = (pilot.return_90d >= 0 ? "+" : "") + pilot.return_90d.toFixed(1) + "%";
  }
  const holds = document.querySelector("#holds");
  Object.entries(pilot.weights).sort((a, b) => b[1] - a[1]).slice(0, 5).forEach(([ticker, weight]) => {
    const row = document.createElement("div");
    row.className = "row";
    const name = document.createElement("b");
    name.textContent = ticker;
    const share = document.createElement("span");
    share.textContent = Math.round(weight * 100) + "%";
    row.append(name, share);
    holds.append(row);
  });
  document.querySelector("#add").href = "/mix.html?add=" + encodeURIComponent(pilot.id);
});
