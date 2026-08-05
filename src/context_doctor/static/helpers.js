/** Pure browser helpers shared by paging behavior and Node unit tests. */
(function (root) {
    'use strict';

    function ruleIdFromHtml(html) {
        // Rule identity is presentation metadata; returning null keeps pages with
        // no conflicts navigable by their ordinal page number.
        var match = String(html || '').match(/Rule\s*#\s*(\d+)/i);
        return match && match[1] ? match[1] : null;
    }

    var helpers = { ruleIdFromHtml: ruleIdFromHtml };
    root.ContextDoctorHelpers = helpers;
    if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
})(typeof window !== 'undefined' ? window : globalThis);
