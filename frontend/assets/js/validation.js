/**
 * Client-side helpers for forms (server-side validation is authoritative).
 */
(function () {
  "use strict";

  window.FuelGuardValidation = {
    nonEmpty: function (v) {
      return typeof v === "string" && v.trim().length > 0;
    },
  };
})();
