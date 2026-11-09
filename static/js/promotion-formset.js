/* Ladder of price breaks on the staff promotion pages.
   Adds a row by cloning the ``<template>`` Django renders from
   ``tier_formset.empty_form`` and removes rows without ever renumbering the
   existing ones: a removed saved break keeps its ``DELETE`` checkbox checked,
   an unsaved row is simply emptied. */
document.addEventListener("DOMContentLoaded", function () {
  const formset = document.querySelector("[data-tier-formset]");
  if (!formset) {
    return;
  }

  const rows = formset.querySelector("[data-tier-rows]");
  const totalForms = formset.querySelector('input[name$="-TOTAL_FORMS"]');
  const addButton = formset.querySelector("[data-tier-add]");
  const template = document.getElementById("tier-row-template");
  if (!rows || !totalForms || !addButton || !template) {
    return;
  }

  function nextIndex() {
    const value = parseInt(totalForms.value, 10);
    return Number.isNaN(value) ? 0 : value;
  }

  addButton.addEventListener("click", function () {
    const index = nextIndex();
    const html = template.innerHTML.replace(/__prefix__/g, index);
    const wrapper = document.createElement("tbody");
    wrapper.innerHTML = html.trim();
    const row = wrapper.querySelector("tr");
    if (!row) {
      return;
    }
    rows.appendChild(row);
    totalForms.value = index + 1;

    const units = row.querySelector("input[type='number']");
    if (units) {
      units.focus();
    }
  });

  rows.addEventListener("click", function (event) {
    const button = event.target.closest("[data-tier-delete]");
    if (!button) {
      return;
    }

    const row = button.closest("tr");
    if (!row) {
      return;
    }
    const idField = row.querySelector("input[name$='-id']");
    const deleteField = row.querySelector("input[name$='-DELETE']");

    if (idField && idField.value) {
      // A saved break: toggle the DELETE checkbox, so a mis-click can be undone
      // before the form is submitted.
      const willDelete = !(deleteField && deleteField.checked);
      if (deleteField) {
        deleteField.checked = willDelete;
      }
      row.classList.toggle("is-removed", willDelete);
      return;
    }

    // An unsaved row: emptying it is enough, the formset skips empty extras.
    row.querySelectorAll("input[type='number']").forEach(function (input) {
      input.value = "";
    });
  });
});
