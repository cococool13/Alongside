const picked = new Map();

function even() {
  const ids = [...picked.keys()];
  if (!ids.length) return;
  const share = Math.round((100 / ids.length) * 10) / 10;
  ids.forEach((id) => { picked.get(id).percent = share; });
  const drift = Math.round((100 - [...picked.values()].reduce((sum, row) => sum + row.percent, 0)) * 10) / 10;
  picked.get(ids[0]).percent = Math.round((picked.get(ids[0]).percent + drift) * 10) / 10;
}

function render() {
  const mix = document.querySelector("#mix");
  const result = document.querySelector("#result");
  mix.replaceChildren();
  result.replaceChildren();
  picked.forEach((row) => {
    const label = document.createElement("label");
    label.append(row.name);
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.value = String(row.percent);
    input.addEventListener("input", () => { row.percent = Number(input.value); render(); });
    label.append(input);
    mix.append(label);
  });
  const rows = [...picked.values()];
  const sum = rows.reduce((total, row) => total + Number(row.percent || 0), 0) || 1;
  const mixed = {};
  rows.forEach((row) => {
    Object.entries(row.weights).forEach(([ticker, weight]) => {
      mixed[ticker] = (mixed[ticker] || 0) + (row.percent / sum) * weight;
    });
  });
  Object.entries(mixed).sort((a, b) => b[1] - a[1]).slice(0, 5).forEach(([ticker, weight]) => {
    const line = document.createElement("div");
    line.className = "row";
    const name = document.createElement("b");
    name.textContent = ticker;
    const share = document.createElement("span");
    share.textContent = Math.round(weight * 100) + "%";
    line.append(name, share);
    result.append(line);
  });
}

function toggle(pilot) {
  if (picked.has(pilot.id)) picked.delete(pilot.id);
  else if (picked.size < 2) picked.set(pilot.id, {name: pilot.name, weights: pilot.weights, percent: 0});
  even();
  document.querySelectorAll("button.pilot").forEach((node) => {
    node.setAttribute("aria-pressed", picked.has(node.dataset.id) ? "true" : "false");
  });
  render();
}

fetch("/pilots.json").then((r) => r.json()).then((data) => {
  const ranked = data.pilots
    .filter((row) => typeof row.return_90d === "number")
    .sort((a, b) => b.return_90d - a.return_90d)
    .slice(0, 5);
  const box = document.querySelector("#choices");
  ranked.forEach((pilot) => {
    const button = document.createElement("button");
    button.className = "pilot";
    button.type = "button";
    button.dataset.id = pilot.id;
    button.textContent = pilot.name;
    button.addEventListener("click", () => toggle(pilot));
    box.append(button);
  });
  const add = new URLSearchParams(location.search).get("add");
  const preset = data.pilots.find((row) => row.id === add);
  if (preset) toggle(preset);
});
