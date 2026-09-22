fetch("/pilots.json").then((r) => r.json()).then((data) => {
  const ranked = data.pilots
    .filter((row) => typeof row.return_90d === "number")
    .sort((a, b) => b.return_90d - a.return_90d)
    .slice(0, 5);
  const list = document.querySelector("#list");
  ranked.forEach((row, index) => {
    const link = document.createElement("a");
    link.className = "row";
    link.href = "/portfolio.html?id=" + encodeURIComponent(row.id);
    const name = document.createElement("b");
    name.textContent = (index + 1) + "  " + row.name;
    const ret = document.createElement("span");
    ret.className = row.return_90d >= 0 ? "chip" : "down";
    ret.textContent = (row.return_90d >= 0 ? "+" : "") + row.return_90d.toFixed(1) + "%";
    link.append(name, ret);
    list.append(link);
  });
});
