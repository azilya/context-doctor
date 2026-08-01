/** Behavior-preserving browser controller for Context Doctor. */
var configNode = document.getElementById('context-doctor-config');
window.CONTEXT_DOCTOR_CONFIG = configNode ? JSON.parse(configNode.textContent) : {};
function showLoading() {
            document.getElementById('loadingOverlay').style.display = 'flex';
        }

        function toggleContextUploadRequirement() {
            var contextId = document.getElementById('context_id');
            var schemaFile = document.getElementById('schema_file');
            var rulesFile = document.getElementById('rules_file');
            if (!contextId || !schemaFile || !rulesFile) return;
            var hasCachedContext = contextId.value.trim() !== '';
            schemaFile.required = !hasCachedContext;
            rulesFile.required = !hasCachedContext;
        }

        function toggleFields() {
            var flow = document.getElementById('flow').value;
            var ruleField = document.getElementById('new_rule_field');
            var questionField = document.getElementById('question_field');
            var problemField = document.getElementById('problem_field');
            var guidelines = document.getElementById('guidelines_details');
            if (flow === 'rule_analysis') {
                ruleField.style.display = 'block';
                questionField.style.display = 'none';
                if (problemField) problemField.style.display = 'none';
                if (guidelines) guidelines.style.display = 'block';
            } else if (flow === 'all_rules_analysis') {
                // For all-rules analysis only the uploaded context is needed
                ruleField.style.display = 'none';
                questionField.style.display = 'none';
                if (problemField) problemField.style.display = 'none';
                if (guidelines) guidelines.style.display = 'block';
            } else if (flow === 'rule_generation') {
                // For rule generation show question and problem inputs
                ruleField.style.display = 'none';
                questionField.style.display = 'block';
                if (problemField) problemField.style.display = 'block';
                if (guidelines) guidelines.style.display = 'block';
            } else {
                ruleField.style.display = 'none';
                questionField.style.display = 'block';
                if (problemField) problemField.style.display = 'none';
                if (guidelines) guidelines.style.display = 'none';
            }
        }

        // Copy the innerText of the <pre> inside the named details block.
        function copyBlock(detailsId, btn) {
            var pre = document.querySelector('#' + detailsId + ' pre');
            if (!pre) return;
            var text = pre.innerText;
            navigator.clipboard.writeText(text).then(function () {
                var old = btn.innerText;
                btn.innerText = 'Copied!';
                setTimeout(function () { btn.innerText = old; }, 1200);
            }, function (err) {
                console.error('Copy failed', err);
            });
        }

        // Clear only the main form fields and redirect to the index page
        function clearAndRedirect() {
            try {
                var flow = document.getElementById('flow');
                if (flow) flow.selectedIndex = 0; // reset to first option
                var ids = ['new_rule', 'question', 'problem'];
                ids.forEach(function(id) {
                    var el = document.getElementById(id);
                    if (el) el.value = '';
                });
                var dialect = document.getElementById('sql_dialect');
                if (dialect) dialect.value = 'PostgreSQL';
                var schemaFile = document.getElementById('schema_file');
                if (schemaFile) schemaFile.value = '';
                var rulesFile = document.getElementById('rules_file');
                if (rulesFile) rulesFile.value = '';
            } catch (e) {
                // ignore
            }
            window.location.href = '/';
        }

document.addEventListener('DOMContentLoaded', function () {
            try {
                toggleFields();
                toggleContextUploadRequirement();
                var contextId = document.getElementById('context_id');
                if (contextId) {
                    contextId.addEventListener('input', toggleContextUploadRequirement);
                    contextId.addEventListener('change', toggleContextUploadRequirement);
                }
            } catch (e) { /* ignore if missing */ }
        });

// Paging for all_rules_analysis results passed as JSON list in `result_pages_json`
var pages = [];
var current = 0;
var ruleIndexMap = {};
var pager = document.getElementById('result_pager');
var container = document.getElementById('result_container');
var prevBtn = document.getElementById('prev_page');
var nextBtn = document.getElementById('next_page');
var indicator = document.getElementById('page_indicator');
var gotoInput = document.getElementById('goto_input');
var gotoBtn = document.getElementById('goto_btn');

function updateRuleIndex(startIndex) {
    for (var i = startIndex; i < pages.length; i++) {
        var html = pages[i] || '';
        var ruleId = window.ContextDoctorHelpers.ruleIdFromHtml(html);
        if (ruleId) {
            ruleIndexMap[String(ruleId)] = i;
        }
    }
}

function renderPage(i) {
    if (!container || !pages.length) return;
    container.innerHTML = pages[i];

    var pageHtml = pages[i] || '';
    var ruleId = window.ContextDoctorHelpers.ruleIdFromHtml(pageHtml);

    if (indicator) indicator.innerText = (i + 1) + ' / ' + pages.length;
    var titleEl = document.getElementById('page_title_top');
    if (titleEl) {
        if (ruleId) titleEl.innerText = 'Rule #' + ruleId;
        else titleEl.innerText = 'Rule ' + (i + 1);
    }

    if (prevBtn) prevBtn.disabled = i === 0;
    if (nextBtn) nextBtn.disabled = i === pages.length - 1;
    if (gotoInput) gotoInput.value = ruleId ? String(ruleId) : (i + 1);
}

function updatePagerVisibility() {
    if (pager) pager.style.display = pages.length > 1 ? 'block' : 'none';
}

function addPages(newPages) {
    if (!newPages || !newPages.length) return;
    var startIndex = pages.length;
    newPages.forEach(function(p) { pages.push(p); });
    updateRuleIndex(startIndex);
    if (pages.length === newPages.length) {
        current = 0;
    }
    updatePagerVisibility();
    renderPage(Math.min(current, pages.length - 1));
}

function resetResultsView(message) {
    pages = [];
    current = 0;
    ruleIndexMap = {};
    if (container) container.innerHTML = message || '<pre>Stopped.</pre>';
    var titleEl = document.getElementById('page_title_top');
    if (titleEl) titleEl.innerText = '';
    updatePagerVisibility();
}

if (prevBtn) {
    prevBtn.addEventListener('click', function() {
        if (current > 0) {
            current -= 1;
            renderPage(current);
        }
    });
}
if (nextBtn) {
    nextBtn.addEventListener('click', function() {
        if (current < pages.length - 1) {
            current += 1;
            renderPage(current);
        }
    });
}
if (gotoBtn && gotoInput) {
    gotoBtn.addEventListener('click', function() {
        var raw = gotoInput.value;
        if (!raw) return;
        var asNum = parseInt(raw, 10);
        var idx = null;

        if (!isNaN(asNum) && ruleIndexMap.hasOwnProperty(String(asNum))) {
            idx = ruleIndexMap[String(asNum)];
        } else if (!isNaN(asNum)) {
            alert('No conflicts in this rule');
        } else if (ruleIndexMap.hasOwnProperty(raw)) {
            idx = ruleIndexMap[raw];
        }

        if (idx === null) return;
        current = idx;
        renderPage(current);
    });
}

var initialPages = window.CONTEXT_DOCTOR_CONFIG.initialPages || [];
if (Array.isArray(initialPages)) addPages(initialPages);

var taskId = window.CONTEXT_DOCTOR_CONFIG.taskId;
var nextIndex = 0;
var pollIntervalMs = 3000;
var pollTimer = null;
var pollStopped = false;
var pollController = null;

function applyContext(data) {
    if (data.rules_text) {
        var rulesPre = document.getElementById('rules_pre');
        if (rulesPre && !rulesPre.innerText) rulesPre.innerText = data.rules_text;
    }
    if (data.schema_json) {
        var schemaPre = document.getElementById('schema_pre');
        if (schemaPre && !schemaPre.innerText) schemaPre.innerText = data.schema_json;
    }
    if (data.guidelines_text) {
        var guidelinesPre = document.getElementById('guidelines_pre');
        if (guidelinesPre && !guidelinesPre.innerText) guidelinesPre.innerText = data.guidelines_text;
    }
}

function updateProgress(data) {
    var progress = document.getElementById('loadingProgress');
    if (!progress) return;
    if (data.total_rules) {
        progress.innerText = 'Analyzing rules: ' + data.completed_rules + ' / ' + data.total_rules;
    } else {
        progress.innerText = 'Preparing analysis...';
    }
}

function showAsyncError(message) {
    var box = document.getElementById('async_error');
    if (!box) return;
    box.style.display = 'block';
    box.innerHTML = '<h2>Error</h2><p>' + message + '</p>';
}

function pollTask() {
    if (pollStopped) return;
    pollController = new AbortController();
    fetch('/tasks/' + taskId + '?from_index=' + nextIndex, { signal: pollController.signal })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (pollStopped) return;
            if (!data || data.status === 'failed') {
                if (data && data.error) showAsyncError(data.error);
                document.getElementById('loadingOverlay').style.display = 'none';
                if (pollTimer) clearTimeout(pollTimer);
                return;
            }

            applyContext(data);
            updateProgress(data);
            if (data.pages && data.pages.length) {
                addPages(data.pages);
                nextIndex = data.next_index || nextIndex + data.pages.length;
            }

            if (data.status === 'completed') {
                document.getElementById('loadingOverlay').style.display = 'none';
                if (pollTimer) clearTimeout(pollTimer);
                return;
            }
            if (data.status === 'cancelled') {
                document.getElementById('loadingOverlay').style.display = 'none';
                if (pollTimer) clearTimeout(pollTimer);
                return;
            }

            pollTimer = setTimeout(pollTask, pollIntervalMs);
        })
        .catch(function(err) {
            if (pollStopped || (err && err.name === 'AbortError')) return;
            console.error('Polling failed', err);
            pollTimer = setTimeout(pollTask, pollIntervalMs);
        });
}

function stopTask() {
    pollStopped = true;
    if (pollTimer) clearTimeout(pollTimer);
    if (pollController) pollController.abort();
    if (taskId) {
        fetch('/tasks/' + taskId + '/cancel', { method: 'POST' }).catch(function() {});
    }
    document.getElementById('loadingOverlay').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', function () {
    // Only task-bearing result pages poll; normal form and synchronous result
    // pages must never request a literal "null" task identifier.
    if (taskId) {
        document.getElementById('loadingOverlay').style.display = 'flex';
        updateProgress({});
        pollTask();
    }
});


// Bind declarative template controls after parsing, keeping templates markup-only.
document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('[data-analysis-form]');
    if (form) form.addEventListener('submit', showLoading);
    var flow = document.querySelector('[data-flow-select]');
    if (flow) flow.addEventListener('change', toggleFields);
    document.querySelectorAll('[data-copy-target]').forEach(function (button) {
        button.addEventListener('click', function () { copyBlock(button.dataset.copyTarget, button); });
    });
    var clear = document.querySelector('[data-action="clear"]');
    if (clear) clear.addEventListener('click', clearAndRedirect);
    var stop = document.querySelector('[data-action="stop-task"]');
    if (stop) stop.addEventListener('click', stopTask);
    var contextId = document.getElementById('context_id');
    if (contextId) contextId.addEventListener('input', function () {
        var reuse = Boolean(contextId.value.trim());
        ['schema_file', 'rules_file'].forEach(function (id) {
            var input = document.getElementById(id);
            if (input) input.required = !reuse;
        });
    });
});
