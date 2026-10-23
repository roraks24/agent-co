/* ============================================================
   Rorak AI — Frontend Application
   ============================================================
   Vanilla JS single-page client for the Rorak AI REST API.
   Endpoints consumed:
     POST   /auth/register | /auth/login     GET /auth/me
     GET    /health/  |  /ready/
     POST   /chat/
     CRUD   /conversations/  (+ /{id}/messages)
     CRUD   /documents/      (uploads are scoped to a conversation)
     CRUD   /memories/
   ============================================================ */

(function () {
    "use strict";

    // ── Configuration ──
    var API_BASE = window.RORAK_API_BASE || (
        window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
            ? (window.location.port === "8000" ? "" : "http://localhost:8000")
            : (window.location.hostname.indexOf("rorak.tech") !== -1 || window.location.hostname.indexOf("web.app") !== -1 || window.location.hostname.indexOf("firebaseapp.com") !== -1
                ? "https://api.rorak.tech"
                : "")
    );

    // ── Greetings ──
    var GREETINGS = [
        "Ready when you are.",
        "What can I help you with?",
        "Ask me anything.",
        "What's on your mind today?",
        "Let's dig into your documents.",
        "Ready to explore your documents."
    ];

    // ── Application State ──
    var messages = [];
    var uploadedFileName = null;
    var activeDocumentId = null;
    var isLoading = false;
    var currentUserId = null;
    var currentUser = null;
    var activeConversationId = null;
    var activeView = "chat"; // "chat" | "docs" | "memory"

    // Authentication & Storage Keys
    var RORAK_TOKEN_KEY = "rorak_access_token";
    var RORAK_USER_KEY = "rorak_user";

    // Document library state
    var docLibrary = {
        documents: [],
        page: 1,
        pageSize: 20,
        total: 0,
        totalPages: 1,
        isLoading: false,
        pendingActionDoc: null
    };

    // Conversation state
    var conversationLibrary = {
        conversations: [],
        isLoading: false,
        pendingActionConv: null
    };

    // Memory state
    var memoryLibrary = {
        memories: [],
        page: 1,
        pageSize: 20,
        total: 0,
        totalPages: 1,
        isLoading: false,
        pendingDeleteMemory: null
    };

    // ── DOM References ──
    var mainArea = document.getElementById("mainArea");
    var emptyState = document.getElementById("emptyState");
    var emptyGreeting = document.getElementById("emptyGreeting");
    var chatMessages = document.getElementById("chatMessages");
    var chatInput = document.getElementById("chatInput");
    var uploadBtn = document.getElementById("uploadBtn");
    var sendBtn = document.getElementById("sendBtn");
    var fileInput = document.getElementById("fileInput");
    var uploadIndicator = document.getElementById("uploadIndicator");
    var notification = document.getElementById("notification");
    var menuToggle = document.getElementById("menuToggle");
    var sidebar = document.getElementById("sidebar");
    var sidebarOverlay = document.getElementById("sidebarOverlay");

    // Navigation & Views
    var navChatBtn = document.getElementById("navChatBtn");
    var navDocsBtn = document.getElementById("navDocsBtn");
    var navMemoryBtn = document.getElementById("navMemoryBtn");
    var docsCountBadge = document.getElementById("docsCountBadge");
    var memoriesCountBadge = document.getElementById("memoriesCountBadge");
    var docsSection = document.getElementById("docsSection");
    var memorySection = document.getElementById("memorySection");
    var inputArea = document.getElementById("inputArea");

    // "Files in chat" DOM
    var chatCornerBar = document.getElementById("chatCornerBar");
    var btnFilesInChat = document.getElementById("btnFilesInChat");
    var chatFilesBadge = document.getElementById("chatFilesBadge");
    var chatFilesDrawer = document.getElementById("chatFilesDrawer");
    var drawerFilesCount = document.getElementById("drawerFilesCount");
    var chatFilesCloseBtn = document.getElementById("chatFilesCloseBtn");

    // Conversations DOM
    var btnNewChat = document.getElementById("btnNewChat");
    var convListContainer = document.getElementById("convListContainer");
    var convList = document.getElementById("convList");

    var convRenameModal = document.getElementById("convRenameModal");
    var convRenameInput = document.getElementById("convRenameInput");
    var convRenameCharCount = document.getElementById("convRenameCharCount");
    var convRenameError = document.getElementById("convRenameError");
    var convRenameCloseBtn = document.getElementById("convRenameCloseBtn");
    var convRenameCancelBtn = document.getElementById("convRenameCancelBtn");
    var convRenameSubmitBtn = document.getElementById("convRenameSubmitBtn");

    var convDeleteModal = document.getElementById("convDeleteModal");
    var deleteConvTitle = document.getElementById("deleteConvTitle");
    var convDeleteCloseBtn = document.getElementById("convDeleteCloseBtn");
    var convDeleteCancelBtn = document.getElementById("convDeleteCancelBtn");
    var convDeleteConfirmBtn = document.getElementById("convDeleteConfirmBtn");

    // Memory DOM
    var memoriesRefreshBtn = document.getElementById("memoriesRefreshBtn");
    var memoriesAddBtn = document.getElementById("memoriesAddBtn");
    var metricTotalMemories = document.getElementById("metricTotalMemories");
    var metricPersonalMemories = document.getElementById("metricPersonalMemories");
    var memoriesList = document.getElementById("memoriesList");
    var memoriesPagination = document.getElementById("memoriesPagination");
    var btnPrevMemPage = document.getElementById("btnPrevMemPage");
    var btnNextMemPage = document.getElementById("btnNextMemPage");
    var memPageIndicator = document.getElementById("memPageIndicator");

    var memoryDeleteModal = document.getElementById("memoryDeleteModal");
    var deleteMemoryPreview = document.getElementById("deleteMemoryPreview");
    var memoryDeleteCloseBtn = document.getElementById("memoryDeleteCloseBtn");
    var memoryDeleteCancelBtn = document.getElementById("memoryDeleteCancelBtn");
    var memoryDeleteConfirmBtn = document.getElementById("memoryDeleteConfirmBtn");

    var memoryAddModal = document.getElementById("memoryAddModal");
    var memoryAddContent = document.getElementById("memoryAddContent");
    var memoryAddType = document.getElementById("memoryAddType");
    var memoryAddScope = document.getElementById("memoryAddScope");
    var memoryAddError = document.getElementById("memoryAddError");
    var memoryAddCloseBtn = document.getElementById("memoryAddCloseBtn");
    var memoryAddCancelBtn = document.getElementById("memoryAddCancelBtn");
    var memoryAddSubmitBtn = document.getElementById("memoryAddSubmitBtn");

    // Document Library DOM
    var docsUploadBtn = document.getElementById("docsUploadBtn");
    var docsRefreshBtn = document.getElementById("docsRefreshBtn");
    var docsUploadProgress = document.getElementById("docsUploadProgress");
    var progressFileName = document.getElementById("progressFileName");
    var progressStatusText = document.getElementById("progressStatusText");
    var progressBar = document.getElementById("progressBar");
    var docsList = document.getElementById("docsList");
    var docsPagination = document.getElementById("docsPagination");
    var btnPrevPage = document.getElementById("btnPrevPage");
    var btnNextPage = document.getElementById("btnNextPage");
    var pageIndicator = document.getElementById("pageIndicator");

    // Metrics
    var metricTotalDocs = document.getElementById("metricTotalDocs");
    var metricTotalPages = document.getElementById("metricTotalPages");

    // Modals
    var docDetailsModal = document.getElementById("docDetailsModal");
    var docDetailsContent = document.getElementById("docDetailsContent");
    var docDetailsCloseBtn = document.getElementById("docDetailsCloseBtn");
    var docDetailsDoneBtn = document.getElementById("docDetailsDoneBtn");

    var docRenameModal = document.getElementById("docRenameModal");
    var renameInput = document.getElementById("renameInput");
    var renameCharCount = document.getElementById("renameCharCount");
    var renameError = document.getElementById("renameError");
    var docRenameCloseBtn = document.getElementById("docRenameCloseBtn");
    var docRenameCancelBtn = document.getElementById("docRenameCancelBtn");
    var docRenameSubmitBtn = document.getElementById("docRenameSubmitBtn");

    var docDeleteModal = document.getElementById("docDeleteModal");
    var deleteDocName = document.getElementById("deleteDocName");
    var docDeleteCloseBtn = document.getElementById("docDeleteCloseBtn");
    var docDeleteCancelBtn = document.getElementById("docDeleteCancelBtn");
    var docDeleteConfirmBtn = document.getElementById("docDeleteConfirmBtn");

    // Authentication DOM
    var authModal = document.getElementById("authModal");
    var authCloseBtn = document.getElementById("authCloseBtn");
    var authSubtitle = document.getElementById("authSubtitle");
    var authTabLogin = document.getElementById("authTabLogin");
    var authTabRegister = document.getElementById("authTabRegister");

    var loginForm = document.getElementById("loginForm");
    var loginEmail = document.getElementById("loginEmail");
    var loginPassword = document.getElementById("loginPassword");
    var loginError = document.getElementById("loginError");
    var loginSubmitBtn = document.getElementById("loginSubmitBtn");
    var toggleLoginPassword = document.getElementById("toggleLoginPassword");
    var switchToRegisterLink = document.getElementById("switchToRegisterLink");

    var registerForm = document.getElementById("registerForm");
    var registerName = document.getElementById("registerName");
    var registerEmail = document.getElementById("registerEmail");
    var registerPassword = document.getElementById("registerPassword");
    var registerConfirmPassword = document.getElementById("registerConfirmPassword");
    var registerError = document.getElementById("registerError");
    var registerSubmitBtn = document.getElementById("registerSubmitBtn");
    var toggleRegisterPassword = document.getElementById("toggleRegisterPassword");
    var switchToLoginLink = document.getElementById("switchToLoginLink");

    var userProfileWidget = document.getElementById("userProfileWidget");
    var sidebarUserAvatar = document.getElementById("sidebarUserAvatar");
    var sidebarUserEmail = document.getElementById("sidebarUserEmail");
    var sidebarLogoutBtn = document.getElementById("sidebarLogoutBtn");
    var sidebarSignInBtn = document.getElementById("sidebarSignInBtn");

    // ── Agent Workspace DOM & State ──
    var navAgentBtn = document.getElementById("navAgentBtn");
    var sidebarConversationsSection = document.getElementById("sidebarConversationsSection");
    var sidebarAgentSection = document.getElementById("sidebarAgentSection");
    var btnNewProject = document.getElementById("btnNewProject");
    var projectListContainer = document.getElementById("projectListContainer");
    var projectList = document.getElementById("projectList");

    var agentWorkspaceSection = document.getElementById("agentWorkspaceSection");
    var currentProjectName = document.getElementById("currentProjectName");
    var agentStatusBadges = document.getElementById("agentStatusBadges");
    var badgeExecution = document.getElementById("badgeExecution");
    var badgeDeliverable = document.getElementById("badgeDeliverable");
    var badgeVerification = document.getElementById("badgeVerification");
    var badgeObjective = document.getElementById("badgeObjective");
    var btnRefreshWorkspace = document.getElementById("btnRefreshWorkspace");
    var btnDownloadZip = document.getElementById("btnDownloadZip");

    var agentObjectiveInput = document.getElementById("agentObjectiveInput");
    var agentTaskTypeSelect = document.getElementById("agentTaskTypeSelect");
    var btnRunAgent = document.getElementById("btnRunAgent");
    var runBtnText = document.getElementById("runBtnText");

    var agentFileTree = document.getElementById("agentFileTree");
    var btnNewFile = document.getElementById("btnNewFile");
    var activeFileName = document.getElementById("activeFileName");
    var fileDirtyIndicator = document.getElementById("fileDirtyIndicator");
    var btnTogglePreview = document.getElementById("btnTogglePreview");
    var btnModeCode = document.getElementById("btnModeCode");
    var btnModePreview = document.getElementById("btnModePreview");
    var btnSaveFile = document.getElementById("btnSaveFile");
    var agentCodeEditor = document.getElementById("agentCodeEditor");
    var workspacePreviewContainer = document.getElementById("workspacePreviewContainer");
    var previewToolbar = document.getElementById("previewToolbar");
    var previewStatusDot = document.getElementById("previewStatusDot");
    var previewAddressText = document.getElementById("previewAddressText");
    var btnViewportDesktop = document.getElementById("btnViewportDesktop");
    var btnViewportTablet = document.getElementById("btnViewportTablet");
    var btnViewportMobile = document.getElementById("btnViewportMobile");
    var btnRefreshPreview = document.getElementById("btnRefreshPreview");
    var btnPopoutPreview = document.getElementById("btnPopoutPreview");
    var btnExpandPreview = document.getElementById("btnExpandPreview");
    var previewViewportWrapper = document.getElementById("previewViewportWrapper");
    var previewViewportFrame = document.getElementById("previewViewportFrame");
    var workspacePreviewIframe = document.getElementById("workspacePreviewIframe");
    var previewDimensionBadge = document.getElementById("previewDimensionBadge");
    var artifactPreviewPane = document.getElementById("artifactPreviewPane");
    var editorStatusText = document.getElementById("editorStatusText");
    var editorCursorPosition = document.getElementById("editorCursorPosition");

    var tabBtnGraph = document.getElementById("tabBtnGraph");
    var tabBtnAudit = document.getElementById("tabBtnAudit");
    var tabBtnPrompts = document.getElementById("tabBtnPrompts");
    var controlTabGraph = document.getElementById("controlTabGraph");
    var controlTabAudit = document.getElementById("controlTabAudit");
    var controlTabPrompts = document.getElementById("controlTabPrompts");

    var nodePlanner = document.getElementById("nodePlanner");
    var nodeArchitect = document.getElementById("nodeArchitect");
    var nodeCoder = document.getElementById("nodeCoder");
    var statusPlanner = document.getElementById("statusPlanner");
    var statusArchitect = document.getElementById("statusArchitect");
    var statusCoder = document.getElementById("statusCoder");

    var streamingLogsConsole = document.getElementById("streamingLogsConsole");
    var btnClearLogs = document.getElementById("btnClearLogs");
    var auditActionsCount = document.getElementById("auditActionsCount");
    var auditTrailList = document.getElementById("auditTrailList");

    var newProjectModal = document.getElementById("newProjectModal");
    var projectNameInput = document.getElementById("projectNameInput");
    var projectDescInput = document.getElementById("projectDescInput");
    var newProjectError = document.getElementById("newProjectError");
    var newProjectCloseBtn = document.getElementById("newProjectCloseBtn");
    var newProjectCancelBtn = document.getElementById("newProjectCancelBtn");
    var newProjectSubmitBtn = document.getElementById("newProjectSubmitBtn");

    var newFileModal = document.getElementById("newFileModal");
    var newFileNameInput = document.getElementById("newFileNameInput");
    var newFileError = document.getElementById("newFileError");
    var newFileCloseBtn = document.getElementById("newFileCloseBtn");
    var newFileCancelBtn = document.getElementById("newFileCancelBtn");
    var newFileSubmitBtn = document.getElementById("newFileSubmitBtn");

    var agentProjects = [];
    var currentProject = null;
    var currentWorkspaceTree = [];
    var activeFilePath = null;
    var fileContentCache = {};
    var fileIsDirty = false;
    var isPreviewActive = false;
    var agentIsRunning = false;

    // ── SVG Templates ──
    var COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    var CHECK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    var PDF_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>';
    var MESSAGE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    var EDIT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>';
    var TRASH_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>';


    // ────────────────────────────────────────
    //  Initialization
    // ────────────────────────────────────────

    function init() {
        setRandomGreeting();
        bindEvents();
        checkHealth();
        initCustomKeys();

        // Restore user profile from storage if available
        var savedUserStr = localStorage.getItem(RORAK_USER_KEY);
        if (savedUserStr) {
            try {
                currentUser = JSON.parse(savedUserStr);
                currentUserId = currentUser ? currentUser.id : null;
            } catch (e) {}
        }
        updateUserProfileUI();

        var token = getAccessToken();
        if (!token) {
            showAuthModal("login");
            return;
        }

        var urlParams = new URLSearchParams(window.location.search);
        var initialConvId = urlParams.get("conversation_id");

        ensureUser()
            .then(function () {
                loadMemoriesCount();
                return loadConversations();
            })
            .then(function () {
                if (initialConvId) {
                    selectConversation(initialConvId, true);
                } else {
                    loadDocuments(1, null);
                }
            })
            .catch(function (e) {
                console.warn("Session initialization error:", e);
                clearAuthSession();
                showAuthModal("login", "Please sign in to continue.");
            });
    }

    function setRandomGreeting() {
        var index = Math.floor(Math.random() * GREETINGS.length);
        if (emptyGreeting) emptyGreeting.textContent = GREETINGS[index];
    }

    // ────────────────────────────────────────
    //  Authentication & Token Management
    // ────────────────────────────────────────

    function getAccessToken() {
        var token = localStorage.getItem(RORAK_TOKEN_KEY);
        if (!token) return null;
        try {
            var parts = token.split(".");
            if (parts.length === 3) {
                var payload = JSON.parse(atob(parts[1]));
                if (payload.exp && Date.now() >= payload.exp * 1000) {
                    clearAuthSession();
                    return null;
                }
            }
        } catch (e) {
            // Malformed token
            clearAuthSession();
            return null;
        }
        return token;
    }

    function setAuthSession(token, user) {
        if (token) {
            localStorage.setItem(RORAK_TOKEN_KEY, token);
        }
        if (user) {
            currentUser = user;
            currentUserId = user.id;
            localStorage.setItem(RORAK_USER_KEY, JSON.stringify(user));
            localStorage.setItem("rorak_user_id", user.id);
        }
        hideNotification();
        updateUserProfileUI();
    }

    function clearAuthSession() {
        localStorage.removeItem(RORAK_TOKEN_KEY);
        localStorage.removeItem(RORAK_USER_KEY);
        localStorage.removeItem("rorak_user_id");
        localStorage.removeItem("rorak_workspace_id"); // legacy key cleanup
        currentUser = null;
        currentUserId = null;
        activeConversationId = null;
        messages = [];
        docLibrary.documents = [];
        conversationLibrary.conversations = [];
        memoryLibrary.memories = [];
        hideNotification();
        updateUserProfileUI();
    }

    function updateUserProfileUI() {
        if (currentUser && currentUser.email) {
            if (userProfileWidget) userProfileWidget.style.display = "flex";
            if (sidebarSignInBtn) sidebarSignInBtn.style.display = "none";
            if (sidebarUserEmail) {
                sidebarUserEmail.textContent = currentUser.name || currentUser.email;
                sidebarUserEmail.title = currentUser.name ? (currentUser.name + " (" + currentUser.email + ")") : currentUser.email;
            }
            if (sidebarUserAvatar) {
                var initial = (currentUser.name || currentUser.email || "U").trim()[0];
                sidebarUserAvatar.textContent = (initial || "U").toUpperCase();
            }
        } else {
            if (userProfileWidget) userProfileWidget.style.display = "none";
            if (sidebarSignInBtn) sidebarSignInBtn.style.display = "flex";
        }
    }

    function apiFetch(url, options) {
        options = options || {};
        var headers = options.headers || {};
        var token = getAccessToken();

        if (typeof headers.append !== "function") {
            options.headers = Object.assign({}, headers);
            if (token) {
                options.headers["Authorization"] = "Bearer " + token;
            }
        } else {
            if (token) {
                headers.set("Authorization", "Bearer " + token);
            }
        }

        return fetch(url, options).then(function (res) {
            if (res.status === 401) {
                var isAuthRoute = url.indexOf("/auth/login") !== -1 || url.indexOf("/auth/register") !== -1;
                if (!isAuthRoute) {
                    handleUnauthorized();
                }
            }
            return res;
        });
    }

    function handleUnauthorized() {
        clearAuthSession();
        startNewChat(true);
        renderConversationList();
        renderDocumentList();
        renderMemoryList();
        showAuthModal("login", "Your session has expired. Please sign in again.");
    }

    // ────────────────────────────────────────
    //  Auth Modal Controller
    // ────────────────────────────────────────

    function showAuthModal(tab, subtitleText) {
        if (!authModal) return;
        hideNotification();
        switchAuthTab(tab || "login");
        if (subtitleText && authSubtitle) {
            authSubtitle.textContent = subtitleText;
        } else if (authSubtitle) {
            authSubtitle.textContent = "Sign in to access your chats, documents, and memories.";
        }
        if (loginError) {
            loginError.style.display = "none";
            loginError.textContent = "";
        }
        if (registerError) {
            registerError.style.display = "none";
            registerError.textContent = "";
        }
        authModal.style.display = "flex";
        setTimeout(function () {
            if (tab === "register" && registerName) {
                registerName.focus();
            } else if (tab === "register" && registerEmail) {
                registerEmail.focus();
            } else if (loginEmail) {
                loginEmail.focus();
            }
        }, 50);
    }

    function hideAuthModal() {
        if (!authModal) return;
        hideNotification();
        authModal.style.display = "none";
        if (loginError) loginError.style.display = "none";
        if (registerError) registerError.style.display = "none";
    }

    function switchAuthTab(tab) {
        var isLogin = tab === "login";
        if (authTabLogin) {
            authTabLogin.classList.toggle("active", isLogin);
            authTabLogin.setAttribute("aria-selected", isLogin ? "true" : "false");
        }
        if (authTabRegister) {
            authTabRegister.classList.toggle("active", !isLogin);
            authTabRegister.setAttribute("aria-selected", !isLogin ? "true" : "false");
        }
        if (loginForm) loginForm.style.display = isLogin ? "flex" : "none";
        if (registerForm) registerForm.style.display = !isLogin ? "flex" : "none";
        if (loginError) loginError.style.display = "none";
        if (registerError) registerError.style.display = "none";
    }

    function togglePasswordVisibility(inputElem, toggleBtn) {
        if (!inputElem || !toggleBtn) return;
        var isPassword = inputElem.type === "password";
        inputElem.type = isPassword ? "text" : "password";
        var eyeOpen = toggleBtn.querySelector(".eye-open");
        var eyeClosed = toggleBtn.querySelector(".eye-closed");
        if (eyeOpen && eyeClosed) {
            eyeOpen.style.display = isPassword ? "none" : "block";
            eyeClosed.style.display = isPassword ? "block" : "none";
        }
    }

    function showAuthError(elem, message) {
        if (!elem) return;
        elem.textContent = message;
        elem.style.display = "block";
    }

    function extractErrorMessage(data, defaultMsg) {
        if (!data) return defaultMsg;
        if (data.detail) {
            if (typeof data.detail === "object" && data.detail.error && data.detail.error.message) {
                return data.detail.error.message;
            }
            if (typeof data.detail === "string") {
                return data.detail;
            }
            if (Array.isArray(data.detail) && data.detail.length > 0) {
                var first = data.detail[0];
                return (first && first.msg) ? first.msg : defaultMsg;
            }
        }
        if (data.error && data.error.message) {
            return data.error.message;
        }
        return defaultMsg;
    }

    function fetchWithTimeout(url, options, timeoutMs) {
        timeoutMs = timeoutMs || 15000;
        var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
        var opts = Object.assign({}, options);
        if (controller) {
            opts.signal = controller.signal;
        }
        var timer = null;
        var timeoutPromise = new Promise(function (_, reject) {
            timer = setTimeout(function () {
                if (controller) controller.abort();
                reject(new Error("Request timed out. Please check that the server is running."));
            }, timeoutMs);
        });
        return Promise.race([
            fetch(url, opts),
            timeoutPromise
        ]).finally(function () {
            if (timer) clearTimeout(timer);
        });
    }

    function setSubmitLoading(btn, isLoadingState, defaultText) {
        if (!btn) return;
        btn.disabled = isLoadingState;
        var span = btn.querySelector("span") || btn;
        span.textContent = defaultText;
    }

    var isAuthSubmitting = false;

    function handleLoginSubmit(e) {
        if (e && typeof e.preventDefault === "function") e.preventDefault();
        if (isAuthSubmitting) return;

        var email = (loginEmail ? loginEmail.value : "").trim().toLowerCase();
        var password = (loginPassword ? loginPassword.value : "");

        if (!email || !password) {
            showAuthError(loginError, "Please enter both email and password.");
            return;
        }

        isAuthSubmitting = true;
        setSubmitLoading(loginSubmitBtn, true, "Signing in...");
        if (loginError) loginError.style.display = "none";

        fetchWithTimeout(API_BASE + "/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        }, 15000)
            .then(function (res) {
                return res.json().then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                }).catch(function () {
                    return { ok: res.ok, status: res.status, data: null };
                });
            })
            .then(function (result) {
                isAuthSubmitting = false;
                setSubmitLoading(loginSubmitBtn, false, "Sign In");
                if (!result.ok) {
                    var msg = "Invalid email or password.";
                    if (result.data) {
                        msg = extractErrorMessage(result.data, msg);
                    }
                    showAuthError(loginError, msg);
                    return;
                }

                var token = result.data.access_token;
                var user = result.data.user;
                setAuthSession(token, user);
                hideAuthModal();
                if (loginPassword) loginPassword.value = "";

                // Decouple data loading from auth catch handler
                setTimeout(postAuthInit, 50);
            })
            .catch(function (err) {
                isAuthSubmitting = false;
                setSubmitLoading(loginSubmitBtn, false, "Sign In");
                var errMsg = (err && err.message) ? err.message : "Network error: Unable to connect to server.";
                showAuthError(loginError, errMsg);
            });
    }

    function handleRegisterSubmit(e) {
        if (e && typeof e.preventDefault === "function") e.preventDefault();
        if (isAuthSubmitting) return;
        var name = (registerName ? registerName.value : "").trim();
        var email = (registerEmail ? registerEmail.value : "").trim().toLowerCase();
        var password = (registerPassword ? registerPassword.value : "");
        var confirmPassword = (registerConfirmPassword ? registerConfirmPassword.value : "");

        if (!name) {
            showAuthError(registerError, "Please enter your name.");
            return;
        }

        var emailRegex = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
        if (!email || !emailRegex.test(email)) {
            showAuthError(registerError, "Please enter a valid email address.");
            return;
        }

        if (password.length < 8) {
            showAuthError(registerError, "Password must be at least 8 characters long.");
            return;
        }

        if (password !== confirmPassword) {
            showAuthError(registerError, "Passwords do not match.");
            return;
        }

        isAuthSubmitting = true;
        setSubmitLoading(registerSubmitBtn, true, "Creating account...");
        if (registerError) registerError.style.display = "none";

        fetchWithTimeout(API_BASE + "/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password, name: name })
        }, 15000)
            .then(function (res) {
                return res.json().then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                }).catch(function () {
                    return { ok: res.ok, status: res.status, data: null };
                });
            })
            .then(function (regResult) {
                if (!regResult.ok) {
                    isAuthSubmitting = false;
                    setSubmitLoading(registerSubmitBtn, false, "Create Account");
                    var msg = "Registration failed.";
                    if (regResult.status === 409) {
                        msg = "An account with this email already exists. Please sign in.";
                    } else if (regResult.data) {
                        msg = extractErrorMessage(regResult.data, msg);
                    }
                    showAuthError(registerError, msg);
                    return;
                }

                // Automatically log in after registration
                return fetchWithTimeout(API_BASE + "/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email, password: password })
                }, 15000)
                    .then(function (res) {
                        return res.json().then(function (data) {
                            return { ok: res.ok, data: data };
                        }).catch(function () {
                            return { ok: res.ok, data: null };
                        });
                    })
                    .then(function (loginResult) {
                        isAuthSubmitting = false;
                        setSubmitLoading(registerSubmitBtn, false, "Create Account");
                        if (!loginResult.ok || !loginResult.data || !loginResult.data.access_token) {
                            showAuthModal("login", "Account created successfully! Please sign in.");
                            return;
                        }
                        var token = loginResult.data.access_token;
                        var user = loginResult.data.user;
                        setAuthSession(token, user);
                        hideAuthModal();
                        if (registerName) registerName.value = "";
                        if (registerEmail) registerEmail.value = "";
                        if (registerPassword) registerPassword.value = "";
                        if (registerConfirmPassword) registerConfirmPassword.value = "";

                        // Decouple data loading from auth catch handler
                        setTimeout(postAuthInit, 50);
                    });
            })
            .catch(function (err) {
                isAuthSubmitting = false;
                setSubmitLoading(registerSubmitBtn, false, "Create Account");
                var errMsg = (err && err.message) ? err.message : "Network error: Unable to connect to server.";
                showAuthError(registerError, errMsg);
            });
    }

    function handleLogout() {
        clearAuthSession();
        startNewChat(true);
        renderConversationList();
        renderDocumentList();
        renderMemoryList();
        hideNotification();
        showAuthModal("login", "Sign in to access your chats, documents, and memories.");
    }

    function postAuthInit() {
        loadDocuments(1, activeConversationId);
        loadMemoriesCount();
        loadConversations().catch(function (e) {
            console.warn("Post-auth data load deferred:", e);
        });
    }

    // ────────────────────────────────────────
    //  User Resolution
    // ────────────────────────────────────────

    function ensureUser() {
        if (currentUser && currentUserId) {
            return Promise.resolve(currentUserId);
        }
        var token = getAccessToken();
        if (!token) {
            showAuthModal("login");
            return Promise.reject(new Error("Authentication required"));
        }

        return fetch(API_BASE + "/auth/me", {
            headers: { "Authorization": "Bearer " + token }
        })
            .then(function (res) {
                if (!res.ok) {
                    throw new Error("Could not resolve authenticated user (" + res.status + ")");
                }
                return res.json();
            })
            .then(function (user) {
                setAuthSession(token, user);
                return currentUserId;
            });
    }


    // ────────────────────────────────────────
    //  Event Bindings
    // ────────────────────────────────────────

    function bindEvents() {
        // Send message
        if (sendBtn) sendBtn.addEventListener("click", handleSend);
        if (chatInput) {
            chatInput.addEventListener("keydown", function (e) {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                }
            });
            chatInput.addEventListener("focus", function () {
                setTimeout(function () {
                    scrollToBottom();
                    window.scrollTo(0, 0);
                }, 150);
            });
        }

        // File upload from chat bar
        if (uploadBtn) {
            uploadBtn.addEventListener("click", function () {
                if (!getAccessToken()) {
                    showAuthModal("login", "Please sign in to upload documents.");
                    return;
                }
                fileInput.click();
            });
        }
        if (fileInput) {
            fileInput.addEventListener("change", handleFileSelect);
        }

        // Navigation
        if (navChatBtn) {
            navChatBtn.addEventListener("click", function (e) {
                e.preventDefault();
                switchView("chat");
                closeSidebar();
            });
        }
        if (navDocsBtn) {
            navDocsBtn.addEventListener("click", function (e) {
                e.preventDefault();
                switchView("docs");
                closeSidebar();
            });
        }
        if (navAgentBtn) {
            navAgentBtn.addEventListener("click", function (e) {
                e.preventDefault();
                switchView("agent");
                closeSidebar();
            });
        }
        if (btnNewProject) {
            btnNewProject.addEventListener("click", function () {
                openNewProjectModal();
            });
        }
        if (newProjectCloseBtn) newProjectCloseBtn.addEventListener("click", closeNewProjectModal);
        if (newProjectCancelBtn) newProjectCancelBtn.addEventListener("click", closeNewProjectModal);
        if (newProjectSubmitBtn) newProjectSubmitBtn.addEventListener("click", submitNewProject);

        if (btnRefreshWorkspace) {
            btnRefreshWorkspace.addEventListener("click", function () {
                loadWorkspaceTree();
            });
        }
        if (btnDownloadZip) {
            btnDownloadZip.addEventListener("click", function () {
                downloadWorkspaceZip();
            });
        }
        if (btnRunAgent) {
            btnRunAgent.addEventListener("click", function () {
                runAgentObjective();
            });
        }
        if (btnNewFile) {
            btnNewFile.addEventListener("click", function () {
                openNewFileModal();
            });
        }
        if (newFileCloseBtn) newFileCloseBtn.addEventListener("click", closeNewFileModal);
        if (newFileCancelBtn) newFileCancelBtn.addEventListener("click", closeNewFileModal);
        if (newFileSubmitBtn) newFileSubmitBtn.addEventListener("click", submitNewFile);

        if (btnSaveFile) {
            btnSaveFile.addEventListener("click", function () {
                saveCurrentFile();
            });
        }
        if (btnTogglePreview) {
            btnTogglePreview.addEventListener("click", function () {
                toggleFilePreview();
            });
        }
        if (btnModeCode) {
            btnModeCode.addEventListener("click", function () {
                setEditorMode("code");
            });
        }
        if (btnModePreview) {
            btnModePreview.addEventListener("click", function () {
                setEditorMode("preview");
            });
        }
        if (btnViewportDesktop) {
            btnViewportDesktop.addEventListener("click", function () {
                setPreviewViewport("desktop");
            });
        }
        if (btnViewportTablet) {
            btnViewportTablet.addEventListener("click", function () {
                setPreviewViewport("tablet");
            });
        }
        if (btnViewportMobile) {
            btnViewportMobile.addEventListener("click", function () {
                setPreviewViewport("mobile");
            });
        }
        if (btnRefreshPreview) {
            btnRefreshPreview.addEventListener("click", function () {
                refreshPreviewIframe(true);
            });
        }
        if (btnPopoutPreview) {
            btnPopoutPreview.addEventListener("click", function () {
                popoutPreview();
            });
        }
        if (btnExpandPreview) {
            btnExpandPreview.addEventListener("click", function () {
                toggleExpandPreview();
            });
        }
        if (btnClearLogs) {
            btnClearLogs.addEventListener("click", function () {
                clearStreamingLogs();
            });
        }

        if (tabBtnGraph) {
            tabBtnGraph.addEventListener("click", function () {
                switchControlTab("graph");
            });
        }
        if (tabBtnAudit) {
            tabBtnAudit.addEventListener("click", function () {
                switchControlTab("audit");
            });
        }
        if (tabBtnPrompts) {
            tabBtnPrompts.addEventListener("click", function () {
                switchControlTab("prompts");
            });
        }

        if (agentCodeEditor) {
            agentCodeEditor.addEventListener("input", function () {
                if (!fileIsDirty && activeFilePath) {
                    fileIsDirty = true;
                    if (fileDirtyIndicator) fileDirtyIndicator.style.display = "inline";
                }
            });
            agentCodeEditor.addEventListener("keydown", function (e) {
                if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                    e.preventDefault();
                    saveCurrentFile();
                }
            });
            agentCodeEditor.addEventListener("keyup", updateEditorCursor);
            agentCodeEditor.addEventListener("click", updateEditorCursor);
        }

        // Conversations events
        if (btnNewChat) {
            btnNewChat.addEventListener("click", function () {
                if (!getAccessToken()) {
                    showAuthModal("login", "Please sign in to start a new chat.");
                    return;
                }
                startNewChat();
                closeSidebar();
            });
        }

        // Conversation Rename Modal
        if (convRenameCloseBtn) convRenameCloseBtn.addEventListener("click", closeConvRenameModal);
        if (convRenameCancelBtn) convRenameCancelBtn.addEventListener("click", closeConvRenameModal);
        if (convRenameSubmitBtn) convRenameSubmitBtn.addEventListener("click", submitConvRename);
        if (convRenameInput) {
            convRenameInput.addEventListener("input", function () {
                var len = convRenameInput.value.length;
                if (convRenameCharCount) convRenameCharCount.textContent = len + " / 255";
                if (convRenameError) convRenameError.style.display = "none";
            });
            convRenameInput.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    e.preventDefault();
                    submitConvRename();
                }
            });
        }

        // Conversation Delete Modal
        if (convDeleteCloseBtn) convDeleteCloseBtn.addEventListener("click", closeConvDeleteModal);
        if (convDeleteCancelBtn) convDeleteCancelBtn.addEventListener("click", closeConvDeleteModal);
        if (convDeleteConfirmBtn) convDeleteConfirmBtn.addEventListener("click", confirmConvDelete);

        // Memory events
        if (navMemoryBtn) {
            navMemoryBtn.addEventListener("click", function (e) {
                e.preventDefault();
                switchView("memory");
                closeSidebar();
            });
        }
        if (memoriesRefreshBtn) {
            memoriesRefreshBtn.addEventListener("click", function () {
                loadMemories(memoryLibrary.page);
            });
        }
        if (memoriesAddBtn) {
            memoriesAddBtn.addEventListener("click", function () {
                if (!getAccessToken()) {
                    showAuthModal("login", "Please sign in to add memories.");
                    return;
                }
                openMemoryAddModal();
            });
        }
        if (btnPrevMemPage) {
            btnPrevMemPage.addEventListener("click", function () {
                if (memoryLibrary.page > 1) {
                    loadMemories(memoryLibrary.page - 1);
                }
            });
        }
        if (btnNextMemPage) {
            btnNextMemPage.addEventListener("click", function () {
                if (memoryLibrary.page < memoryLibrary.totalPages) {
                    loadMemories(memoryLibrary.page + 1);
                }
            });
        }

        // Memory Delete Modal
        if (memoryDeleteCloseBtn) memoryDeleteCloseBtn.addEventListener("click", closeMemoryDeleteModal);
        if (memoryDeleteCancelBtn) memoryDeleteCancelBtn.addEventListener("click", closeMemoryDeleteModal);
        if (memoryDeleteConfirmBtn) memoryDeleteConfirmBtn.addEventListener("click", confirmDeleteMemory);

        // Memory Add Modal
        if (memoryAddCloseBtn) memoryAddCloseBtn.addEventListener("click", closeMemoryAddModal);
        if (memoryAddCancelBtn) memoryAddCancelBtn.addEventListener("click", closeMemoryAddModal);
        if (memoryAddSubmitBtn) memoryAddSubmitBtn.addEventListener("click", submitAddMemory);

        // "Files in chat" Drawer toggle & close
        if (btnFilesInChat) {
            btnFilesInChat.addEventListener("click", function () {
                toggleChatFilesDrawer();
            });
        }
        if (chatFilesCloseBtn) {
            chatFilesCloseBtn.addEventListener("click", function () {
                toggleChatFilesDrawer(false);
            });
        }

        // Document Library / Files actions
        if (docsUploadBtn) {
            docsUploadBtn.addEventListener("click", function () {
                if (!getAccessToken()) {
                    showAuthModal("login", "Please sign in to upload documents.");
                    return;
                }
                fileInput.click();
            });
        }
        if (docsRefreshBtn) {
            docsRefreshBtn.addEventListener("click", function () {
                loadDocuments(docLibrary.page, activeConversationId);
            });
        }

        // Pagination
        if (btnPrevPage) {
            btnPrevPage.addEventListener("click", function () {
                if (docLibrary.page > 1) {
                    loadDocuments(docLibrary.page - 1);
                }
            });
        }
        if (btnNextPage) {
            btnNextPage.addEventListener("click", function () {
                if (docLibrary.page < docLibrary.totalPages) {
                    loadDocuments(docLibrary.page + 1);
                }
            });
        }

        // Details Modal
        if (docDetailsCloseBtn) docDetailsCloseBtn.addEventListener("click", closeDetailsModal);
        if (docDetailsDoneBtn) docDetailsDoneBtn.addEventListener("click", closeDetailsModal);

        // Rename Modal
        if (docRenameCloseBtn) docRenameCloseBtn.addEventListener("click", closeRenameModal);
        if (docRenameCancelBtn) docRenameCancelBtn.addEventListener("click", closeRenameModal);
        if (docRenameSubmitBtn) docRenameSubmitBtn.addEventListener("click", submitRename);
        if (renameInput) {
            renameInput.addEventListener("input", function () {
                var len = renameInput.value.length;
                if (renameCharCount) renameCharCount.textContent = len + " / 255";
                if (renameError) renameError.style.display = "none";
            });
            renameInput.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    e.preventDefault();
                    submitRename();
                }
            });
        }

        // Delete Modal
        if (docDeleteCloseBtn) docDeleteCloseBtn.addEventListener("click", closeDeleteModal);
        if (docDeleteCancelBtn) docDeleteCancelBtn.addEventListener("click", closeDeleteModal);
        if (docDeleteConfirmBtn) docDeleteConfirmBtn.addEventListener("click", confirmDelete);

        // Authentication Events
        if (authCloseBtn) {
            authCloseBtn.addEventListener("click", function () {
                hideAuthModal();
            });
        }
        if (authTabLogin) {
            authTabLogin.addEventListener("click", function () {
                switchAuthTab("login");
            });
        }
        if (authTabRegister) {
            authTabRegister.addEventListener("click", function () {
                switchAuthTab("register");
            });
        }
        if (switchToRegisterLink) {
            switchToRegisterLink.addEventListener("click", function (e) {
                e.preventDefault();
                switchAuthTab("register");
            });
        }
        if (switchToLoginLink) {
            switchToLoginLink.addEventListener("click", function (e) {
                e.preventDefault();
                switchAuthTab("login");
            });
        }
        if (loginForm) {
            loginForm.addEventListener("submit", handleLoginSubmit);
        }
        if (registerForm) {
            registerForm.addEventListener("submit", handleRegisterSubmit);
        }
        if (toggleLoginPassword) {
            toggleLoginPassword.addEventListener("click", function () {
                togglePasswordVisibility(loginPassword, toggleLoginPassword);
            });
        }
        if (toggleRegisterPassword) {
            toggleRegisterPassword.addEventListener("click", function () {
                togglePasswordVisibility(registerPassword, toggleRegisterPassword);
            });
        }
        if (sidebarSignInBtn) {
            sidebarSignInBtn.addEventListener("click", function () {
                showAuthModal("login");
                closeSidebar();
            });
        }
        if (sidebarLogoutBtn) {
            sidebarLogoutBtn.addEventListener("click", function () {
                handleLogout();
                closeSidebar();
            });
        }

        // Backdrop click to close modals
        [
            docDetailsModal,
            docRenameModal,
            docDeleteModal,
            convRenameModal,
            convDeleteModal,
            memoryDeleteModal,
            memoryAddModal
        ].forEach(function (modal) {
            if (modal) {
                modal.addEventListener("click", function (e) {
                    if (e.target === modal) {
                        modal.style.display = "none";
                    }
                });
            }
        });

        if (authModal) {
            authModal.addEventListener("click", function (e) {
                if (e.target === authModal && getAccessToken()) {
                    hideAuthModal();
                }
            });
        }

        // Browser navigation history restoration (Back / Forward)
        window.addEventListener("popstate", function (e) {
            var urlParams = new URLSearchParams(window.location.search);
            var convId = urlParams.get("conversation_id");
            if (convId) {
                selectConversation(convId, true);
            } else {
                startNewChat(true);
            }
        });

        // Mobile sidebar
        if (menuToggle) menuToggle.addEventListener("click", toggleSidebar);
        if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);
        var sidebarCloseBtn = document.getElementById("sidebarCloseBtn");
        if (sidebarCloseBtn) sidebarCloseBtn.addEventListener("click", closeSidebar);

        if (window.visualViewport) {
            window.visualViewport.addEventListener("resize", function () {
                scrollToBottom();
                window.scrollTo(0, 0);
            });
        }
    }


    // ────────────────────────────────────────
    //  View Switching
    // ────────────────────────────────────────

    function switchView(view) {
        activeView = view;

        if (view === "chat") {
            if (navChatBtn) navChatBtn.classList.add("active");
            if (navDocsBtn) navDocsBtn.classList.remove("active");
            if (navMemoryBtn) navMemoryBtn.classList.remove("active");
            if (navAgentBtn) navAgentBtn.classList.remove("active");

            if (sidebarConversationsSection) sidebarConversationsSection.style.display = "";
            if (sidebarAgentSection) sidebarAgentSection.style.display = "none";
            if (agentWorkspaceSection) agentWorkspaceSection.style.display = "none";

            if (docsSection) docsSection.style.display = "none";
            if (memorySection) memorySection.style.display = "none";
            if (inputArea) inputArea.style.display = "";
            if (chatCornerBar) chatCornerBar.style.display = "flex";

            if (messages.length === 0) {
                if (mainArea) mainArea.classList.add("is-empty");
                if (emptyState) emptyState.style.display = "";
                if (chatMessages) {
                    chatMessages.style.display = "none";
                    chatMessages.classList.remove("active");
                }
            } else {
                if (mainArea) mainArea.classList.remove("is-empty");
                if (emptyState) emptyState.style.display = "none";
                if (chatMessages) {
                    chatMessages.style.display = "";
                    chatMessages.classList.add("active");
                }
            }
        } else if (view === "docs") {
            // "docs" view is now embedded directly inside the chat as "Files in chat"
            switchView("chat");
            toggleChatFilesDrawer(true);
        } else if (view === "memory") {
            if (navMemoryBtn) navMemoryBtn.classList.add("active");
            if (navChatBtn) navChatBtn.classList.remove("active");
            if (navDocsBtn) navDocsBtn.classList.remove("active");
            if (navAgentBtn) navAgentBtn.classList.remove("active");

            if (sidebarConversationsSection) sidebarConversationsSection.style.display = "";
            if (sidebarAgentSection) sidebarAgentSection.style.display = "none";
            if (agentWorkspaceSection) agentWorkspaceSection.style.display = "none";

            toggleChatFilesDrawer(false);
            if (chatCornerBar) chatCornerBar.style.display = "none";

            if (mainArea) mainArea.classList.remove("is-empty");
            if (emptyState) emptyState.style.display = "none";
            if (chatMessages) chatMessages.style.display = "none";
            if (inputArea) inputArea.style.display = "none";

            if (docsSection) docsSection.style.display = "none";
            if (memorySection) memorySection.style.display = "flex";
            loadMemories(memoryLibrary.page);
        } else if (view === "agent") {
            if (navAgentBtn) navAgentBtn.classList.add("active");
            if (navChatBtn) navChatBtn.classList.remove("active");
            if (navDocsBtn) navDocsBtn.classList.remove("active");
            if (navMemoryBtn) navMemoryBtn.classList.remove("active");

            if (sidebarConversationsSection) sidebarConversationsSection.style.display = "none";
            if (sidebarAgentSection) sidebarAgentSection.style.display = "block";

            toggleChatFilesDrawer(false);
            if (chatCornerBar) chatCornerBar.style.display = "none";

            if (mainArea) mainArea.classList.remove("is-empty");
            if (emptyState) emptyState.style.display = "none";
            if (chatMessages) chatMessages.style.display = "none";
            if (inputArea) inputArea.style.display = "none";

            if (docsSection) docsSection.style.display = "none";
            if (memorySection) memorySection.style.display = "none";

            if (agentWorkspaceSection) agentWorkspaceSection.style.display = "flex";
            initAgentWorkspace();
        }
    }


    // ────────────────────────────────────────
    //  "Files in chat" Drawer & Isolation
    // ────────────────────────────────────────

    function toggleChatFilesDrawer(force) {
        if (!chatFilesDrawer) return;
        var isCurrentlyOpen = chatFilesDrawer.classList.contains("open") && chatFilesDrawer.style.display !== "none";
        var shouldOpen = (force !== undefined) ? !!force : !isCurrentlyOpen;
        if (shouldOpen) {
            chatFilesDrawer.style.display = "flex";
            requestAnimationFrame(function () {
                chatFilesDrawer.classList.add("open");
            });
            loadDocuments(1, activeConversationId);
        } else {
            chatFilesDrawer.classList.remove("open");
            setTimeout(function () {
                if (!chatFilesDrawer.classList.contains("open")) {
                    chatFilesDrawer.style.display = "none";
                }
            }, 250);
        }
    }

    function ensureActiveConversation() {
        if (activeConversationId) {
            return Promise.resolve(activeConversationId);
        }
        return apiFetch(API_BASE + "/conversations/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: "New Chat" })
        })
        .then(function (res) {
            if (!res.ok) throw new Error("Failed to initialize conversation for file upload");
            return res.json();
        })
        .then(function (conv) {
            activeConversationId = conv.id;
            var url = new URL(window.location);
            url.searchParams.set("conversation_id", conv.id);
            window.history.pushState({ conversation_id: conv.id }, "", url);
            loadConversations();
            return conv.id;
        });
    }

    function loadDocuments(page, convId) {
        docLibrary.isLoading = true;
        docLibrary.page = page || 1;
        var targetConvId = (convId !== undefined) ? convId : activeConversationId;

        if (!targetConvId) {
            docLibrary.documents = [];
            docLibrary.total = 0;
            docLibrary.totalPages = 1;
            docLibrary.isLoading = false;
            renderDocumentList();
            updateMetrics();
            return Promise.resolve();
        }

        if (docsList && docLibrary.documents.length === 0) {
            docsList.innerHTML = '<div class="docs-loading-state"><p>Loading files…</p></div>';
        }

        var url = API_BASE + "/documents/?page=" + encodeURIComponent(docLibrary.page) +
            "&page_size=" + encodeURIComponent(docLibrary.pageSize);
        if (targetConvId) {
            url += "&conversation_id=" + encodeURIComponent(targetConvId);
        }
        return apiFetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to load documents (" + res.status + ")");
                return res.json();
            })
            .then(function (data) {
                docLibrary.documents = data.documents || [];
                if (data.pagination) {
                    docLibrary.total = data.pagination.total;
                    docLibrary.totalPages = Math.max(1, data.pagination.total_pages);
                } else {
                    docLibrary.total = docLibrary.documents.length;
                    docLibrary.totalPages = 1;
                }
                renderDocumentList();
                updateMetrics();
            })
            .catch(function (err) {
                console.error("Document load error:", err);
                if (docsList) {
                    docsList.innerHTML =
                        '<div class="docs-error-state">' +
                            '<p style="color:#f87171;">Failed to load files.</p>' +
                            '<button class="btn-secondary" id="btnRetryLoad">Retry</button>' +
                        '</div>';
                    var retryBtn = document.getElementById("btnRetryLoad");
                    if (retryBtn) {
                        retryBtn.addEventListener("click", function () {
                            loadDocuments(docLibrary.page, targetConvId);
                        });
                    }
                }
            })
            .finally(function () {
                docLibrary.isLoading = false;
            });
    }

    function renderDocumentList() {
        if (!docsList) return;

        if (docLibrary.documents.length === 0) {
            docsList.innerHTML =
                '<div class="docs-empty-state">' +
                    '<div class="docs-empty-icon">' +
                        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="width:24px;height:24px;flex-shrink:0;">' +
                            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>' +
                            '<polyline points="14 2 14 8 20 8"></polyline>' +
                            '<line x1="12" y1="18" x2="12" y2="12"></line>' +
                            '<line x1="9" y1="15" x2="15" y2="15"></line>' +
                        '</svg>' +
                    '</div>' +
                    '<h3 class="docs-empty-title">No files in this chat</h3>' +
                    '<p class="docs-empty-desc">Upload files through the chat input to ground AI responses in this conversation.</p>' +
                '</div>';

            if (docsPagination) docsPagination.style.display = "none";
            return;
        }

        docsList.innerHTML = "";

        docLibrary.documents.forEach(function (doc) {
            var card = createDocumentCard(doc);
            docsList.appendChild(card);
        });

        // Pagination controls update
        if (docsPagination) {
            if (docLibrary.totalPages > 1) {
                docsPagination.style.display = "flex";
                if (pageIndicator) {
                    pageIndicator.textContent = "Page " + docLibrary.page + " of " + docLibrary.totalPages;
                }
                if (btnPrevPage) btnPrevPage.disabled = (docLibrary.page <= 1);
                if (btnNextPage) btnNextPage.disabled = (docLibrary.page >= docLibrary.totalPages);
            } else {
                docsPagination.style.display = "none";
            }
        }
    }

    function getDocumentIcon(filename) {
        var ext = (filename || "").split(".").pop().toLowerCase();
        if (ext === "csv") {
            return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line><line x1="12" y1="9" x2="12" y2="21"></line></svg>';
        }
        if (ext === "docx" || ext === "doc") {
            return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>';
        }
        if (ext === "md" || ext === "txt") {
            return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>';
        }
        return PDF_ICON;
    }

    function createDocumentCard(doc) {
        var card = document.createElement("div");
        card.className = "doc-card";
        card.dataset.id = doc.id;

        // Top info
        var top = document.createElement("div");
        top.className = "doc-card-top";

        var fileName = doc.original_filename || doc.filename || doc.display_name || "Untitled";

        var icon = document.createElement("div");
        icon.className = "doc-icon-badge";
        icon.innerHTML = getDocumentIcon(fileName);
        top.appendChild(icon);

        var titleArea = document.createElement("div");
        titleArea.className = "doc-title-area";

        var nameEl = document.createElement("div");
        nameEl.className = "doc-display-name";
        nameEl.textContent = fileName;
        titleArea.appendChild(nameEl);

        top.appendChild(titleArea);
        card.appendChild(top);

        // Metadata row
        var meta = document.createElement("div");
        meta.className = "doc-card-meta";

        if (doc.file_size !== undefined && doc.file_size !== null) {
            var sizePill = document.createElement("span");
            sizePill.className = "meta-pill";
            sizePill.textContent = formatBytes(doc.file_size);
            meta.appendChild(sizePill);
        }

        var pagesPill = document.createElement("span");
        pagesPill.className = "meta-pill";
        pagesPill.textContent = (doc.page_count || 0) + " pages";
        meta.appendChild(pagesPill);

        if (doc.created_at) {
            var timePill = document.createElement("span");
            timePill.className = "meta-pill";
            timePill.textContent = formatDate(doc.created_at);
            meta.appendChild(timePill);
        }

        card.appendChild(meta);

        // Actions
        var actions = document.createElement("div");
        actions.className = "doc-card-actions";

        var detailsBtn = document.createElement("button");
        detailsBtn.className = "btn-doc-action";
        detailsBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg> Details';
        detailsBtn.addEventListener("click", function () {
            openDetailsModal(doc.id);
        });
        actions.appendChild(detailsBtn);

        var renameBtn = document.createElement("button");
        renameBtn.className = "btn-doc-action";
        renameBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg> Rename';
        renameBtn.addEventListener("click", function () {
            openRenameModal(doc);
        });
        actions.appendChild(renameBtn);

        var deleteBtn = document.createElement("button");
        deleteBtn.className = "btn-doc-action action-delete";
        deleteBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> Delete';
        deleteBtn.addEventListener("click", function () {
            openDeleteModal(doc);
        });
        actions.appendChild(deleteBtn);

        card.appendChild(actions);
        return card;
    }

    function updateMetrics() {
        var total = docLibrary.total || docLibrary.documents.length;
        var pages = 0;

        docLibrary.documents.forEach(function (d) {
            pages += (d.page_count || 0);
        });

        if (metricTotalDocs) metricTotalDocs.textContent = total;
        if (metricTotalPages) metricTotalPages.textContent = pages;
        if (docsCountBadge) docsCountBadge.textContent = total;
        if (chatFilesBadge) {
            chatFilesBadge.textContent = total;
            if (total > 0) {
                chatFilesBadge.classList.add("has-files");
            } else {
                chatFilesBadge.classList.remove("has-files");
            }
        }
        if (drawerFilesCount) drawerFilesCount.textContent = total;
    }


    // ────────────────────────────────────────
    //  Document Upload with Progress
    // ────────────────────────────────────────

    function handleFileSelect(e) {
        var file = e.target.files[0];
        if (!file) return;

        fileInput.value = "";

        var SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".csv"];
        var ext = "." + file.name.split(".").pop().toLowerCase();
        if (!SUPPORTED_EXTENSIONS.includes(ext)) {
            showNotification(
                "Unsupported file type. Supported formats: PDF, DOCX, TXT, Markdown, CSV."
            );
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            showNotification("File exceeds 10 MB maximum allowed upload size.");
            return;
        }

        uploadDocumentFile(file);
    }

    function uploadDocumentFile(file) {
        var token = getAccessToken();
        if (!token) {
            showAuthModal("login", "Please sign in to upload documents.");
            return;
        }

        showUploadProgress(file.name);
        if (uploadBtn) uploadBtn.disabled = true;
        if (docsUploadBtn) docsUploadBtn.disabled = true;

        ensureActiveConversation()
            .then(function (convId) {
                var formData = new FormData();
                formData.append("file", file);

                var xhr = new XMLHttpRequest();
                var uploadUrl = API_BASE + "/documents/upload";
                if (convId) {
                    uploadUrl += "?conversation_id=" + encodeURIComponent(convId);
                }

                xhr.open("POST", uploadUrl, true);
                if (token) {
                    xhr.setRequestHeader("Authorization", "Bearer " + token);
                }

                    // Real progress tracking
                    xhr.upload.onprogress = function (event) {
                        if (event.lengthComputable) {
                            var percent = Math.round((event.loaded / event.total) * 100);
                            updateProgressBar(percent, "Uploading (" + percent + "%)…");
                        }
                    };

                    xhr.onload = function () {
                        hideUploadProgress();
                        if (uploadBtn) uploadBtn.disabled = false;
                        if (docsUploadBtn) docsUploadBtn.disabled = false;

                        if (xhr.status === 401) {
                            handleUnauthorized();
                            return;
                        }

                        if (xhr.status >= 200 && xhr.status < 300) {
                            try {
                                var data = JSON.parse(xhr.responseText);
                                var doc = data.document || data;
                                var fileName = doc.original_filename || doc.filename || doc.display_name || file.name;

                                uploadedFileName = fileName;
                                activeDocumentId = doc.id;
                                renderUploadChip(fileName);

                                showNotification("Document indexed successfully. Ready for questions!");
                                setTimeout(hideNotification, 4000);

                                // Refresh files in chat silently in the background
                                loadDocuments(1, activeConversationId);
                            } catch (err) {
                                showNotification("Document uploaded, but could not parse response.");
                                loadDocuments(1, activeConversationId);
                            }
                        } else {
                            var errMsg = "Upload failed (" + xhr.status + ")";
                            try {
                                var errData = JSON.parse(xhr.responseText);
                                errMsg = errData.detail || (errData.error && errData.error.message) || errMsg;
                            } catch (e) {}
                            showNotification("Upload failed: " + errMsg);
                        }
                    };

                    xhr.onerror = function () {
                        hideUploadProgress();
                        if (uploadBtn) uploadBtn.disabled = false;
                        if (docsUploadBtn) docsUploadBtn.disabled = false;
                        showNotification("Network error occurred during document upload.");
                    };

                    xhr.send(formData);
            })
            .catch(function (err) {
                hideUploadProgress();
                if (uploadBtn) uploadBtn.disabled = false;
                if (docsUploadBtn) docsUploadBtn.disabled = false;
                showNotification("Could not start upload: " + (err.message || err));
            });
    }

    function showUploadProgress(fileName) {
        if (progressFileName) progressFileName.textContent = fileName;
        if (progressStatusText) progressStatusText.textContent = "Uploading (0%)…";
        if (progressBar) progressBar.style.width = "0%";
        if (docsUploadProgress) docsUploadProgress.style.display = "block";
        showNotification("Uploading " + fileName + "…");
    }

    function updateProgressBar(percent, statusText) {
        if (progressBar) progressBar.style.width = percent + "%";
        if (progressStatusText) progressStatusText.textContent = statusText;
    }

    function hideUploadProgress() {
        if (docsUploadProgress) docsUploadProgress.style.display = "none";
    }

    function renderUploadChip(name) {
        if (!uploadIndicator) return;
        uploadIndicator.innerHTML =
            '<div class="upload-chip">' +
                '<span>📄 ' + escapeHtml(name) + '</span>' +
                '<button class="upload-chip-remove" title="Unlink from chat">&times;</button>' +
            '</div>';
        uploadIndicator.classList.add("active");

        var removeBtn = uploadIndicator.querySelector(".upload-chip-remove");
        if (removeBtn) {
            removeBtn.addEventListener("click", function () {
                uploadedFileName = null;
                activeDocumentId = null;
                uploadIndicator.innerHTML = "";
                uploadIndicator.classList.remove("active");
                showNotification("Document unlinked from active chat session.");
                setTimeout(hideNotification, 2000);
            });
        }
    }


    // ────────────────────────────────────────
    //  Document Details Modal
    // ────────────────────────────────────────

    function openDetailsModal(documentId) {
        if (!docDetailsModal || !docDetailsContent) return;

        docDetailsContent.innerHTML = '<p style="color:#888;">Fetching document metadata…</p>';
        docDetailsModal.style.display = "flex";

        apiFetch(API_BASE + "/documents/" + encodeURIComponent(documentId))
            .then(function (res) {
                if (!res.ok) throw new Error("Document not found (" + res.status + ")");
                return res.json();
            })
            .then(function (doc) {
                renderDetailsContent(doc);
            })
            .catch(function (err) {
                docDetailsContent.innerHTML = '<p style="color:#f87171;">Failed to load details: ' + escapeHtml(err.message) + '</p>';
            });
    }

    function renderDetailsContent(doc) {
        // Excludes storage_key, raw filesystem paths, secrets, or internal tracebacks
        var fileName = doc.original_filename || doc.filename || doc.display_name || "—";
        var html = '<table class="meta-table">' +
            '<tr><td>File Name</td><td><strong>' + escapeHtml(fileName) + '</strong></td></tr>' +
            '<tr><td>File Size</td><td>' + formatBytes(doc.file_size) + ' (' + (doc.file_size || 0).toLocaleString() + ' bytes)</td></tr>' +
            '<tr><td>Pages</td><td>' + (doc.page_count !== undefined ? doc.page_count : "—") + '</td></tr>' +
            '<tr><td>MIME Type</td><td><code>' + escapeHtml(doc.mime_type || "application/pdf") + '</code></td></tr>' +
            '<tr><td>Created</td><td>' + formatDate(doc.created_at, true) + '</td></tr>' +
            '<tr><td>Updated</td><td>' + formatDate(doc.updated_at, true) + '</td></tr>' +
            '</table>';

        docDetailsContent.innerHTML = html;
    }

    function closeDetailsModal() {
        if (docDetailsModal) docDetailsModal.style.display = "none";
    }


    // ────────────────────────────────────────
    //  Document Rename Modal
    // ────────────────────────────────────────

    function openRenameModal(doc) {
        docLibrary.pendingActionDoc = doc;
        if (!docRenameModal || !renameInput) return;

        renameInput.value = doc.original_filename || doc.filename || doc.display_name || "";
        if (renameCharCount) renameCharCount.textContent = renameInput.value.length + " / 255";
        if (renameError) renameError.style.display = "none";

        docRenameModal.style.display = "flex";
        setTimeout(function () {
            renameInput.focus();
            renameInput.select();
        }, 100);
    }

    function closeRenameModal() {
        if (docRenameModal) docRenameModal.style.display = "none";
        docLibrary.pendingActionDoc = null;
    }

    function submitRename() {
        var doc = docLibrary.pendingActionDoc;
        if (!doc || !renameInput) return;

        var newName = renameInput.value.trim();

        if (!newName) {
            showRenameError("File name cannot be empty.");
            return;
        }

        if (newName.length > 255) {
            showRenameError("File name must be 255 characters or fewer.");
            return;
        }

        if (docRenameSubmitBtn) {
            docRenameSubmitBtn.disabled = true;
            docRenameSubmitBtn.textContent = "Saving…";
        }

        apiFetch(API_BASE + "/documents/" + encodeURIComponent(doc.id), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ display_name: newName })
        })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok) {
                        var msg = (data && data.error && data.error.message) || data.detail || "Rename failed";
                        throw new Error(msg);
                    }
                    return data;
                });
            })
            .then(function (updated) {
                closeRenameModal();
                var updatedFileName = updated.original_filename || updated.filename || updated.display_name;
                showNotification("Document renamed to \"" + updatedFileName + "\"");
                setTimeout(hideNotification, 3000);

                // Update in active chip if present
                if (activeDocumentId === updated.id) {
                    uploadedFileName = updatedFileName;
                    renderUploadChip(updatedFileName);
                }

                // Refresh document list
                loadDocuments(docLibrary.page);
            })
            .catch(function (err) {
                showRenameError(err.message || "Failed to rename document.");
            })
            .finally(function () {
                if (docRenameSubmitBtn) {
                    docRenameSubmitBtn.disabled = false;
                    docRenameSubmitBtn.textContent = "Save";
                }
            });
    }

    function showRenameError(msg) {
        if (!renameError) return;
        renameError.textContent = msg;
        renameError.style.display = "block";
    }


    // ────────────────────────────────────────
    //  Document Delete Modal
    // ────────────────────────────────────────

    function openDeleteModal(doc) {
        docLibrary.pendingActionDoc = doc;
        if (!docDeleteModal || !deleteDocName) return;

        deleteDocName.textContent = '"' + (doc.original_filename || doc.filename || doc.display_name || "this document") + '"';
        docDeleteModal.style.display = "flex";
    }

    function closeDeleteModal() {
        if (docDeleteModal) docDeleteModal.style.display = "none";
        docLibrary.pendingActionDoc = null;
    }

    function confirmDelete() {
        var doc = docLibrary.pendingActionDoc;
        if (!doc) return;

        if (docDeleteConfirmBtn) {
            docDeleteConfirmBtn.disabled = true;
            docDeleteConfirmBtn.textContent = "Deleting…";
        }

        // Call per-document DELETE endpoint; never global /documents/clear
        apiFetch(API_BASE + "/documents/" + encodeURIComponent(doc.id), {
            method: "DELETE"
        })
            .then(function (res) {
                if (!res.ok && res.status !== 204) {
                    throw new Error("Failed to delete document (" + res.status + ")");
                }
                closeDeleteModal();
                showNotification("Document deleted.");
                setTimeout(hideNotification, 3000);

                // Remove chip if this was active
                if (activeDocumentId === doc.id) {
                    uploadedFileName = null;
                    activeDocumentId = null;
                    if (uploadIndicator) {
                        uploadIndicator.innerHTML = "";
                        uploadIndicator.classList.remove("active");
                    }
                }

                loadDocuments(docLibrary.page);
            })
            .catch(function (err) {
                showNotification("Delete failed: " + (err.message || err));
            })
            .finally(function () {
                if (docDeleteConfirmBtn) {
                    docDeleteConfirmBtn.disabled = false;
                    docDeleteConfirmBtn.textContent = "Delete Permanently";
                }
            });
    }


    // ────────────────────────────────────────
    //  Conversation Experience
    // ────────────────────────────────────────

    function loadConversations() {
        conversationLibrary.isLoading = true;
        if (convList && conversationLibrary.conversations.length === 0) {
            convList.innerHTML = '<div class="conv-loading-state">Loading chats…</div>';
        }

        var url = API_BASE + "/conversations/?page=1&page_size=50";
        return apiFetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to load conversations (" + res.status + ")");
                return res.json();
            })
            .then(function (data) {
                conversationLibrary.conversations = data.conversations || [];
                renderConversationList();
                return conversationLibrary.conversations;
            })
            .catch(function (err) {
                console.error("Conversation load error:", err);
                if (convList) {
                    convList.innerHTML =
                        '<div class="conv-error-state">' +
                            '<p style="color:#f87171;">Could not load chats.</p>' +
                            '<button class="btn-secondary" id="btnRetryConvs">Retry</button>' +
                        '</div>';
                    var retryBtn = document.getElementById("btnRetryConvs");
                    if (retryBtn) retryBtn.addEventListener("click", loadConversations);
                }
            })
            .finally(function () {
                conversationLibrary.isLoading = false;
            });
    }

    function renderConversationList() {
        if (!convList) return;

        if (conversationLibrary.conversations.length === 0) {
            convList.innerHTML = '<div class="conv-empty-state">No conversations yet</div>';
            return;
        }

        convList.innerHTML = "";
        conversationLibrary.conversations.forEach(function (conv) {
            var item = document.createElement("div");
            item.className = "conv-item" + (conv.id === activeConversationId ? " active" : "");
            item.dataset.id = conv.id;

            var left = document.createElement("div");
            left.className = "conv-item-left";
            left.innerHTML = '<span class="conv-icon">' + MESSAGE_ICON + '</span>' +
                '<span class="conv-title" title="' + escapeHtml(conv.title) + '">' + escapeHtml(conv.title) + '</span>';
            item.appendChild(left);

            var actions = document.createElement("div");
            actions.className = "conv-actions";

            var renameBtn = document.createElement("button");
            renameBtn.className = "conv-action-btn";
            renameBtn.title = "Rename conversation";
            renameBtn.innerHTML = EDIT_ICON;
            renameBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                openConvRenameModal(conv);
            });
            actions.appendChild(renameBtn);

            var deleteBtn = document.createElement("button");
            deleteBtn.className = "conv-action-btn action-delete";
            deleteBtn.title = "Delete conversation";
            deleteBtn.innerHTML = TRASH_ICON;
            deleteBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                openConvDeleteModal(conv);
            });
            actions.appendChild(deleteBtn);

            item.appendChild(actions);

            item.addEventListener("click", function () {
                selectConversation(conv.id);
            });

            convList.appendChild(item);
        });
    }

    function selectConversation(convId, skipHistoryPush) {
        if (activeConversationId === convId && activeView === "chat") {
            return;
        }
        activeConversationId = convId;

        if (!skipHistoryPush) {
            var url = new URL(window.location);
            url.searchParams.set("conversation_id", convId);
            window.history.pushState({ conversation_id: convId }, "", url);
        }

        switchView("chat");
        renderConversationList();
        closeSidebar();
        loadConversationMessages(convId);
        loadDocuments(1, convId);
    }

    function startNewChat(skipHistoryPush) {
        activeConversationId = null;
        messages = [];
        if (chatMessages) {
            chatMessages.innerHTML = "";
            chatMessages.style.display = "none";
            chatMessages.classList.remove("active");
        }

        uploadedFileName = null;
        activeDocumentId = null;
        if (uploadIndicator) {
            uploadIndicator.innerHTML = "";
            uploadIndicator.classList.remove("active");
        }

        if (!skipHistoryPush) {
            var url = new URL(window.location);
            url.searchParams.delete("conversation_id");
            window.history.pushState({}, "", url);
        }

        renderConversationList();
        switchView("chat");
        setRandomGreeting();
        loadDocuments(1, null);
        toggleChatFilesDrawer(false);
        if (chatInput) chatInput.focus();
    }

    function loadConversationMessages(convId) {
        if (!chatMessages) return;

        uploadedFileName = null;
        activeDocumentId = null;
        if (uploadIndicator) {
            uploadIndicator.innerHTML = "";
            uploadIndicator.classList.remove("active");
        }

        chatMessages.innerHTML =
            '<div class="chat-loading-history">' +
                '<div class="loading-dots"><span></span><span></span><span></span></div>' +
                '<span>Restoring conversation history…</span>' +
            '</div>';
        chatMessages.style.display = "";
        chatMessages.classList.add("active");
        if (emptyState) emptyState.style.display = "none";
        if (mainArea) mainArea.classList.remove("is-empty");

        var url = API_BASE + "/conversations/" + encodeURIComponent(convId) + "/messages?page=1&page_size=100";
        apiFetch(url)
            .then(function (res) {
                if (res.status === 404) {
                    // Deleted conversation state: gracefully recover
                    showNotification("This conversation no longer exists or was deleted.");
                    startNewChat(false);
                    loadConversations();
                    return null;
                }
                if (!res.ok) throw new Error("Failed to load messages (" + res.status + ")");
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                chatMessages.innerHTML = "";
                messages = [];
                var list = data.messages || [];
                if (list.length === 0) {
                    if (mainArea) mainArea.classList.add("is-empty");
                    if (emptyState) emptyState.style.display = "";
                    chatMessages.style.display = "none";
                    return;
                }

                list.forEach(function (msg) {
                    messages.push({ role: msg.role, content: msg.content });
                    renderMessage(msg.role, msg.content, formatDate(msg.created_at, true), true);
                });
                scrollToBottom();
            })
            .catch(function (err) {
                console.error("Messages load error:", err);
                finishChat();
                chatMessages.innerHTML =
                    '<div class="conv-error-state">' +
                        '<p style="color:#f87171;">Failed to load messages.</p>' +
                        '<button class="btn-secondary" id="btnRetryMessages">Retry</button>' +
                    '</div>';
                var retryBtn = document.getElementById("btnRetryMessages");
                if (retryBtn) {
                    retryBtn.addEventListener("click", function () {
                        loadConversationMessages(convId);
                    });
                }
            });
    }

    function openConvRenameModal(conv) {
        conversationLibrary.pendingActionConv = conv;
        if (!convRenameModal || !convRenameInput) return;
        convRenameInput.value = conv.title || "";
        if (convRenameCharCount) convRenameCharCount.textContent = (conv.title || "").length + " / 255";
        if (convRenameError) convRenameError.style.display = "none";
        convRenameModal.style.display = "flex";
        setTimeout(function () { convRenameInput.focus(); }, 100);
    }

    function closeConvRenameModal() {
        if (convRenameModal) convRenameModal.style.display = "none";
        conversationLibrary.pendingActionConv = null;
    }

    function submitConvRename() {
        var conv = conversationLibrary.pendingActionConv;
        if (!conv || !convRenameInput) return;

        var newTitle = convRenameInput.value.trim();
        if (!newTitle) {
            showConvRenameError("Title cannot be empty.");
            return;
        }
        if (newTitle.length > 255) {
            showConvRenameError("Title exceeds 255 characters.");
            return;
        }

        if (convRenameSubmitBtn) {
            convRenameSubmitBtn.disabled = true;
            convRenameSubmitBtn.textContent = "Saving…";
        }

        var url = API_BASE + "/conversations/" + encodeURIComponent(conv.id);
        apiFetch(url, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: newTitle })
        })
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to rename conversation (" + res.status + ")");
                return res.json();
            })
            .then(function (updated) {
                closeConvRenameModal();
                showNotification("Conversation renamed.");
                setTimeout(hideNotification, 2500);

                var idx = conversationLibrary.conversations.findIndex(function (c) { return c.id === conv.id; });
                if (idx !== -1) {
                    conversationLibrary.conversations[idx].title = updated.title;
                }
                renderConversationList();
            })
            .catch(function (err) {
                showConvRenameError(err.message || "Failed to rename conversation.");
            })
            .finally(function () {
                if (convRenameSubmitBtn) {
                    convRenameSubmitBtn.disabled = false;
                    convRenameSubmitBtn.textContent = "Save";
                }
            });
    }

    function showConvRenameError(msg) {
        if (!convRenameError) return;
        convRenameError.textContent = msg;
        convRenameError.style.display = "block";
    }

    function openConvDeleteModal(conv) {
        conversationLibrary.pendingActionConv = conv;
        if (!convDeleteModal || !deleteConvTitle) return;
        deleteConvTitle.textContent = '"' + (conv.title || "this conversation") + '"';
        convDeleteModal.style.display = "flex";
    }

    function closeConvDeleteModal() {
        if (convDeleteModal) convDeleteModal.style.display = "none";
        conversationLibrary.pendingActionConv = null;
    }

    function confirmConvDelete() {
        var conv = conversationLibrary.pendingActionConv;
        if (!conv) return;

        if (convDeleteConfirmBtn) {
            convDeleteConfirmBtn.disabled = true;
            convDeleteConfirmBtn.textContent = "Deleting…";
        }

        var url = API_BASE + "/conversations/" + encodeURIComponent(conv.id);
        apiFetch(url, { method: "DELETE" })
            .then(function (res) {
                if (!res.ok && res.status !== 200 && res.status !== 204) {
                    throw new Error("Failed to delete conversation (" + res.status + ")");
                }
                closeConvDeleteModal();
                showNotification("Conversation deleted.");
                setTimeout(hideNotification, 2500);

                if (activeConversationId === conv.id) {
                    startNewChat();
                }
                return loadConversations();
            })
            .catch(function (err) {
                showNotification("Delete failed: " + (err.message || err));
            })
            .finally(function () {
                if (convDeleteConfirmBtn) {
                    convDeleteConfirmBtn.disabled = false;
                    convDeleteConfirmBtn.textContent = "Delete Permanently";
                }
            });
    }


    // ────────────────────────────────────────
    //  Memory UI Experience
    // ────────────────────────────────────────

    function loadMemoriesCount() {
        var url = API_BASE + "/memories/?page=1&page_size=1";
        return apiFetch(url)
            .then(function (res) {
                if (!res.ok) return null;
                return res.json();
            })
            .then(function (data) {
                if (data && data.pagination && memoriesCountBadge) {
                    memoriesCountBadge.textContent = data.pagination.total;
                }
            })
            .catch(function (e) {
                console.warn("Memories count load error:", e);
            });
    }

    function loadMemories(page) {
        memoryLibrary.isLoading = true;
        memoryLibrary.page = page || 1;

        if (memoriesList && memoryLibrary.memories.length === 0) {
            memoriesList.innerHTML = '<div class="docs-loading-state"><p>Loading memories…</p></div>';
        }

        var url = API_BASE + "/memories/?page=" + encodeURIComponent(memoryLibrary.page) +
            "&page_size=" + encodeURIComponent(memoryLibrary.pageSize);
        return apiFetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to load memories (" + res.status + ")");
                return res.json();
            })
            .then(function (data) {
                memoryLibrary.memories = data.memories || [];
                if (data.pagination) {
                    memoryLibrary.total = data.pagination.total;
                    memoryLibrary.totalPages = Math.max(1, data.pagination.total_pages);
                } else {
                    memoryLibrary.total = memoryLibrary.memories.length;
                    memoryLibrary.totalPages = 1;
                }
                if (memoriesCountBadge) {
                    memoriesCountBadge.textContent = memoryLibrary.total;
                }
                renderMemoryList();
                updateMemoryMetrics();
            })
            .catch(function (err) {
                console.error("Memories load error:", err);
                if (memoriesList) {
                    memoriesList.innerHTML =
                        '<div class="docs-error-state">' +
                            '<p style="color:#f87171;">Failed to load memories.</p>' +
                            '<button class="btn-secondary" id="btnRetryMemories">Retry</button>' +
                        '</div>';
                    var retryBtn = document.getElementById("btnRetryMemories");
                    if (retryBtn) {
                        retryBtn.addEventListener("click", function () {
                            loadMemories(memoryLibrary.page);
                        });
                    }
                }
            })
            .finally(function () {
                memoryLibrary.isLoading = false;
            });
    }

    function updateMemoryMetrics() {
        if (metricTotalMemories) metricTotalMemories.textContent = memoryLibrary.total;
        if (metricPersonalMemories) metricPersonalMemories.textContent = memoryLibrary.total;
    }

    function renderMemoryList() {
        if (!memoriesList) return;

        if (memoryLibrary.memories.length === 0) {
            memoriesList.innerHTML =
                '<div class="docs-empty-state">' +
                    '<div class="docs-empty-icon">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
                            '<path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-10 0V7a5 5 0 0 1 5-5z"></path>' +
                            '<path d="M19 11v1a7 7 0 0 1-14 0v-1"></path>' +
                            '<line x1="12" y1="19" x2="12" y2="22"></line>' +
                            '<line x1="8" y1="22" x2="16" y2="22"></line>' +
                        '</svg>' +
                    '</div>' +
                    '<h3 class="docs-empty-title">No memories stored yet</h3>' +
                    '<p class="docs-empty-desc">Rorak AI captures user preferences and durable facts to assemble rich context during chat conversations.</p>' +
                    '<button class="btn-primary" id="btnEmptyAddMem">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                            '<line x1="12" y1="5" x2="12" y2="19"></line>' +
                            '<line x1="5" y1="12" x2="19" y2="12"></line>' +
                        '</svg>' +
                        'Add First Memory' +
                    '</button>' +
                '</div>';

            var emptyAddBtn = document.getElementById("btnEmptyAddMem");
            if (emptyAddBtn) emptyAddBtn.addEventListener("click", openMemoryAddModal);
            if (memoriesPagination) memoriesPagination.style.display = "none";
            return;
        }

        memoriesList.innerHTML = "";
        memoryLibrary.memories.forEach(function (mem) {
            var card = createMemoryCard(mem);
            memoriesList.appendChild(card);
        });

        // Pagination
        if (memoriesPagination) {
            if (memoryLibrary.totalPages > 1) {
                memoriesPagination.style.display = "flex";
                if (memPageIndicator) {
                    memPageIndicator.textContent = "Page " + memoryLibrary.page + " of " + memoryLibrary.totalPages;
                }
                if (btnPrevMemPage) btnPrevMemPage.disabled = (memoryLibrary.page <= 1);
                if (btnNextMemPage) btnNextMemPage.disabled = (memoryLibrary.page >= memoryLibrary.totalPages);
            } else {
                memoriesPagination.style.display = "none";
            }
        }
    }

    function createMemoryCard(mem) {
        var card = document.createElement("div");
        card.className = "memory-card";
        card.dataset.id = mem.id;

        var top = document.createElement("div");
        top.className = "memory-card-top";

        var badges = document.createElement("div");
        badges.className = "memory-card-badges";

        var typeBadge = document.createElement("span");
        typeBadge.className = "badge-type";
        typeBadge.textContent = formatMemoryType(mem.memory_type);
        badges.appendChild(typeBadge);

        top.appendChild(badges);

        var deleteBtn = document.createElement("button");
        deleteBtn.className = "btn-doc-action action-delete";
        deleteBtn.title = "Delete Memory";
        deleteBtn.innerHTML = TRASH_ICON + "<span>Delete</span>";
        deleteBtn.addEventListener("click", function () {
            openMemoryDeleteModal(mem);
        });
        top.appendChild(deleteBtn);

        card.appendChild(top);

        var contentBox = document.createElement("div");
        contentBox.className = "memory-content-box";
        contentBox.textContent = mem.content;
        card.appendChild(contentBox);

        var footer = document.createElement("div");
        footer.className = "memory-card-footer";
        var dateEl = document.createElement("span");
        dateEl.textContent = "Added " + formatDate(mem.created_at, true);
        footer.appendChild(dateEl);
        card.appendChild(footer);

        return card;
    }

    function formatMemoryType(typeStr) {
        if (!typeStr) return "Directive";
        return typeStr
            .split("_")
            .map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); })
            .join(" ");
    }

    function openMemoryDeleteModal(mem) {
        memoryLibrary.pendingDeleteMemory = mem;
        if (!memoryDeleteModal || !deleteMemoryPreview) return;
        deleteMemoryPreview.textContent = '"' + mem.content + '"';
        memoryDeleteModal.style.display = "flex";
    }

    function closeMemoryDeleteModal() {
        if (memoryDeleteModal) memoryDeleteModal.style.display = "none";
        memoryLibrary.pendingDeleteMemory = null;
    }

    function confirmDeleteMemory() {
        var mem = memoryLibrary.pendingDeleteMemory;
        if (!mem) return;

        if (memoryDeleteConfirmBtn) {
            memoryDeleteConfirmBtn.disabled = true;
            memoryDeleteConfirmBtn.textContent = "Deleting…";
        }

        var url = API_BASE + "/memories/" + encodeURIComponent(mem.id);
        apiFetch(url, { method: "DELETE" })
            .then(function (res) {
                if (!res.ok && res.status !== 200 && res.status !== 204) {
                    throw new Error("Failed to delete memory (" + res.status + ")");
                }
                closeMemoryDeleteModal();
                showNotification("Memory deleted.");
                setTimeout(hideNotification, 2500);
                loadMemories(memoryLibrary.page);
            })
            .catch(function (err) {
                showNotification("Delete memory failed: " + (err.message || err));
            })
            .finally(function () {
                if (memoryDeleteConfirmBtn) {
                    memoryDeleteConfirmBtn.disabled = false;
                    memoryDeleteConfirmBtn.textContent = "Delete Permanently";
                }
            });
    }

    function openMemoryAddModal() {
        if (!memoryAddModal || !memoryAddContent) return;
        memoryAddContent.value = "";
        if (memoryAddError) memoryAddError.style.display = "none";
        memoryAddModal.style.display = "flex";
        setTimeout(function () { memoryAddContent.focus(); }, 100);
    }

    function closeMemoryAddModal() {
        if (memoryAddModal) memoryAddModal.style.display = "none";
    }

    function submitAddMemory() {
        if (!memoryAddContent) return;
        var content = memoryAddContent.value.trim();
        if (!content) {
            if (memoryAddError) {
                memoryAddError.textContent = "Content cannot be empty.";
                memoryAddError.style.display = "block";
            }
            return;
        }

        var type = memoryAddType ? memoryAddType.value : "system_directive";

        if (memoryAddSubmitBtn) {
            memoryAddSubmitBtn.disabled = true;
            memoryAddSubmitBtn.textContent = "Saving…";
        }

        var payload = {
            content: content,
            memory_type: type
        };
        apiFetch(API_BASE + "/memories/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to save memory (" + res.status + ")");
                return res.json();
            })
            .then(function () {
                closeMemoryAddModal();
                showNotification("Memory saved.");
                setTimeout(hideNotification, 2500);
                loadMemories(1);
            })
            .catch(function (err) {
                if (memoryAddError) {
                    memoryAddError.textContent = err.message || "Failed to save memory.";
                    memoryAddError.style.display = "block";
                }
            })
            .finally(function () {
                if (memoryAddSubmitBtn) {
                    memoryAddSubmitBtn.disabled = false;
                    memoryAddSubmitBtn.textContent = "Save Memory";
                }
            });
    }


    // ────────────────────────────────────────
    //  Chat Logic (Preserved V1 Experience & Continuity)
    // ────────────────────────────────────────

    function handleSend() {
        if (!getAccessToken()) {
            showAuthModal("login", "Please sign in to send messages.");
            return;
        }

        var question = chatInput.value.trim();

        if (!question) {
            chatInput.classList.add("shake");
            setTimeout(function () {
                chatInput.classList.remove("shake");
            }, 400);
            return;
        }

        if (isLoading) return;

        hideNotification();
        addMessage("user", question);
        chatInput.value = "";

        uploadedFileName = null;
        activeDocumentId = null;
        if (uploadIndicator) {
            uploadIndicator.innerHTML = "";
            uploadIndicator.classList.remove("active");
        }

        isLoading = true;
        sendBtn.disabled = true;
        var loadingId = showLoadingDots();
        var convIdAtStart = activeConversationId;

        executeChatWithRetry(question, 0, loadingId, convIdAtStart);
    }

    function executeChatWithRetry(question, retryCount, loadingId, convIdAtStart) {
        var MAX_RETRIES = 2;
        var RETRY_DELAYS = [1000, 2000];

        var customKeys = getActiveCustomKeys();
        var payload = {
            question: question
        };
        if (convIdAtStart) {
            payload.conversation_id = convIdAtStart;
        }
        if (customKeys) {
            payload.custom_keys = customKeys;
        }

        apiFetch(API_BASE + "/chat/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok) {
                        var errObj = new Error((data && data.error && data.error.message) || data.detail || "Chat request failed");
                        errObj.status = res.status;
                        throw errObj;
                    }
                    return data;
                });
            })
            .then(function (data) {
                removeLoadingDots(loadingId);
                hideNotification();

                // If user switched conversations while request was in-flight, do not append to new conversation
                if (convIdAtStart !== null && activeConversationId !== convIdAtStart) {
                    loadConversations();
                    finishChat();
                    return;
                }

                if (!activeConversationId && data.conversation_id) {
                    activeConversationId = data.conversation_id;
                    var url = new URL(window.location);
                    url.searchParams.set("conversation_id", activeConversationId);
                    window.history.replaceState({ conversation_id: activeConversationId }, "", url);
                    loadConversations();
                    loadDocuments(1, activeConversationId);
                }
                addMessage("assistant", data.answer);
                finishChat();
                loadMemoriesCount();
                if (activeView === "memory") {
                    loadMemories(memoryLibrary.page);
                }
            })
            .catch(function (error) {
                var isTransient = !error.status || error.status >= 500;

                if (isTransient && retryCount < MAX_RETRIES) {
                    var delay = RETRY_DELAYS[retryCount];
                    var nextAttempt = retryCount + 1;
                    showNotification("Temporary backend issue. Retrying in " + (delay / 1000) + "s… (Attempt " + nextAttempt + "/" + MAX_RETRIES + ")");

                    setTimeout(function () {
                        executeChatWithRetry(question, retryCount + 1, loadingId, convIdAtStart);
                    }, delay);
                } else {
                    removeLoadingDots(loadingId);
                    var userMessage = error.message || "Something went wrong. Please try again.";
                    showNotification(userMessage);
                    finishChat();
                }
            });
    }

    function finishChat() {
        isLoading = false;
        if (sendBtn) sendBtn.disabled = false;
        if (chatInput) chatInput.focus();
    }

    function addMessage(role, content) {
        messages.push({ role: role, content: content });
        renderMessage(role, content, getCurrentTime(), false);
    }

    function renderMessage(role, content, timestamp, skipAutoScroll) {
        if (activeView === "chat") {
            if (mainArea) mainArea.classList.remove("is-empty");
            if (emptyState) emptyState.style.display = "none";
            if (chatMessages) {
                chatMessages.style.display = "";
                chatMessages.classList.add("active");
            }
        }

        var msgEl = document.createElement("div");
        msgEl.className = "message message-" + role;

        var headerEl = document.createElement("div");
        headerEl.className = "message-header";

        if (role === "assistant") {
            var avatarEl = document.createElement("div");
            avatarEl.className = "message-avatar";
            avatarEl.textContent = "R";
            headerEl.appendChild(avatarEl);
        }

        var labelEl = document.createElement("div");
        labelEl.className = "message-label";
        labelEl.textContent = role === "user" ? "YOU" : "RORAK";
        headerEl.appendChild(labelEl);

        msgEl.appendChild(headerEl);

        var contentEl = document.createElement("div");
        contentEl.className = "message-content markdown-body";
        contentEl.innerHTML = formatContent(content, role);
        msgEl.appendChild(contentEl);

        if (role === "assistant") {
            var footerEl = document.createElement("div");
            footerEl.className = "message-footer";

            var timeEl = document.createElement("span");
            timeEl.className = "message-time";
            timeEl.textContent = timestamp || getCurrentTime();
            footerEl.appendChild(timeEl);

            var copyBtn = document.createElement("button");
            copyBtn.className = "btn-copy";
            copyBtn.title = "Copy";
            copyBtn.innerHTML = COPY_ICON;
            copyBtn.addEventListener("click", function () {
                copyToClipboard(content, copyBtn);
            });
            footerEl.appendChild(copyBtn);

            msgEl.appendChild(footerEl);
        }

        if (chatMessages) chatMessages.appendChild(msgEl);
        if (!skipAutoScroll) scrollToBottom();
    }

    function formatContent(text, role) {
        if (role === "user") {
            var safe = escapeHtml(text);
            return safe.replace(/\n/g, "<br>");
        }

        if (window.marked && window.DOMPurify) {
            try {
                var rawHtml = window.marked.parse(text, {
                    breaks: true,
                    gfm: true
                });
                return window.DOMPurify.sanitize(rawHtml);
            } catch (e) {}
        }

        var safeText = escapeHtml(text);
        safeText = safeText.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        safeText = safeText.replace(/\n/g, "<br>");
        return safeText;
    }

    function getCurrentTime() {
        var now = new Date();
        var hours = now.getHours();
        var minutes = now.getMinutes();
        var ampm = hours >= 12 ? "PM" : "AM";
        hours = hours % 12;
        hours = hours ? hours : 12;
        minutes = minutes < 10 ? "0" + minutes : minutes;
        return hours + ":" + minutes + " " + ampm;
    }

    function copyToClipboard(text, btn) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                showCopied(btn);
            }).catch(function () {
                fallbackCopy(text, btn);
            });
        } else {
            fallbackCopy(text, btn);
        }
    }

    function fallbackCopy(text, btn) {
        var textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand("copy");
            showCopied(btn);
        } catch (e) {}
        document.body.removeChild(textarea);
    }

    function showCopied(btn) {
        btn.innerHTML = CHECK_ICON;
        btn.classList.add("copied");
        setTimeout(function () {
            btn.innerHTML = COPY_ICON;
            btn.classList.remove("copied");
        }, 2000);
    }

    function showLoadingDots() {
        var id = "loading-" + Date.now();

        var msgEl = document.createElement("div");
        msgEl.className = "message message-assistant";
        msgEl.id = id;

        var headerEl = document.createElement("div");
        headerEl.className = "message-header";

        var avatarEl = document.createElement("div");
        avatarEl.className = "message-avatar";
        avatarEl.textContent = "R";
        headerEl.appendChild(avatarEl);

        var labelEl = document.createElement("div");
        labelEl.className = "message-label";
        labelEl.textContent = "RORAK";
        headerEl.appendChild(labelEl);

        var dotsEl = document.createElement("div");
        dotsEl.className = "loading-dots";
        dotsEl.innerHTML = "<span></span><span></span><span></span>";

        msgEl.appendChild(headerEl);
        msgEl.appendChild(dotsEl);
        chatMessages.appendChild(msgEl);

        scrollToBottom();
        return id;
    }

    function removeLoadingDots(id) {
        var el = document.getElementById(id);
        if (el) el.remove();
    }

    function scrollToBottom() {
        requestAnimationFrame(function () {
            if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }


    // ────────────────────────────────────────
    //  Health & Notifications
    // ────────────────────────────────────────

    function checkHealth() {
        fetch(API_BASE + "/health/")
            .then(function (res) {
                if (!res.ok) throw new Error("unhealthy");
                return res.json();
            })
            .then(function (data) {
                if (data.status !== "healthy") {
                    showNotification("Backend service is initializing. Some features may take a moment.");
                }
            })
            .catch(function () {
                showNotification("Cannot connect to server. Ensure the backend is reachable.");
            });
    }

    function showNotification(message) {
        if (!notification) return;
        notification.textContent = message;
        notification.classList.add("active");
    }

    function hideNotification() {
        if (!notification) return;
        notification.classList.remove("active");
        notification.textContent = "";
    }


    // ────────────────────────────────────────
    //  Mobile Sidebar
    // ────────────────────────────────────────

    function toggleSidebar() {
        if (!sidebar) return;
        var isOpen = sidebar.classList.contains("open");
        if (isOpen) {
            closeSidebar();
        } else {
            sidebar.classList.add("open");
            if (sidebarOverlay) sidebarOverlay.classList.add("active");
        }
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove("open");
        if (sidebarOverlay) sidebarOverlay.classList.remove("active");
    }


    // ────────────────────────────────────────
    //  Formatters & Helpers
    // ────────────────────────────────────────

    function formatBytes(bytes) {
        if (bytes === 0 || bytes === undefined || bytes === null) return "0 B";
        var k = 1024;
        var sizes = ["B", "KB", "MB", "GB"];
        var i = Math.floor(Math.log(bytes) / Math.log(k));
        var value = (bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 1);
        return value + " " + sizes[i];
    }

    function formatDate(isoStr, includeTime) {
        if (!isoStr) return "—";
        try {
            var d = new Date(isoStr);
            if (isNaN(d.getTime())) return isoStr;
            var opts = { month: "short", day: "numeric", year: "numeric" };
            if (includeTime) {
                opts.hour = "numeric";
                opts.minute = "2-digit";
            }
            return d.toLocaleDateString(undefined, opts);
        } catch (e) {
            return isoStr;
        }
    }

    function escapeHtml(text) {
        if (text === null || text === undefined) return "";
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }


    // ─────────────────────────────────────────────────────────────────────────
    //  Agent Workspace & 3-Pane IDE Controller
    // ─────────────────────────────────────────────────────────────────────────

    var auditActionRecords = [];

    function initAgentWorkspace() {
        loadProjects();
    }

    function loadProjects() {
        return apiFetch(API_BASE + "/api/agent/projects")
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to load projects (" + res.status + ")");
                return res.json();
            })
            .then(function (projects) {
                agentProjects = (projects && projects.projects) ? projects.projects : (projects || []);
                if (agentProjects.length === 0) {
                    return createDefaultProject();
                } else {
                    renderProjectsList();
                    var savedId = localStorage.getItem("rorak_agent_project_id");
                    var match = agentProjects.find(function (p) { return p.id === savedId; });
                    selectProject(match || agentProjects[0]);
                }
            })
            .catch(function (err) {
                console.error("loadProjects error:", err);
            });
    }

    function createDefaultProject() {
        return apiFetch(API_BASE + "/api/agent/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: "Agent Co Project",
                description: "Integrated cloud development and research workspace"
            })
        })
            .then(function (res) { return res.json(); })
            .then(function (proj) {
                agentProjects = [proj];
                renderProjectsList();
                selectProject(proj);
            });
    }

    function renderProjectsList() {
        if (!projectList) return;
        projectList.innerHTML = "";
        agentProjects.forEach(function (proj) {
            var item = document.createElement("div");
            item.className = "conv-item" + (currentProject && currentProject.id === proj.id ? " active" : "");
            item.dataset.id = proj.id;

            var titleSpan = document.createElement("span");
            titleSpan.className = "conv-title";
            titleSpan.textContent = proj.name || "Untitled Project";
            titleSpan.title = proj.description || proj.name;

            var actionsDiv = document.createElement("div");
            actionsDiv.className = "conv-actions";

            var delBtn = document.createElement("button");
            delBtn.className = "conv-action-btn btn-delete";
            delBtn.title = "Delete Project";
            delBtn.innerHTML = TRASH_ICON;
            delBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                if (confirm("Delete project '" + proj.name + "' and its workspace?")) {
                    deleteProject(proj.id);
                }
            });

            actionsDiv.appendChild(delBtn);
            item.appendChild(titleSpan);
            item.appendChild(actionsDiv);

            item.addEventListener("click", function () {
                selectProject(proj);
                closeSidebar();
            });

            projectList.appendChild(item);
        });
    }

    function selectProject(proj) {
        currentProject = proj;
        if (proj) {
            localStorage.setItem("rorak_agent_project_id", proj.id);
            if (currentProjectName) currentProjectName.textContent = proj.name;
        }
        renderProjectsList();
        loadWorkspaceTree();
        resetPipelineNodes();
    }

    function deleteProject(projId) {
        apiFetch(API_BASE + "/api/agent/projects/" + projId, { method: "DELETE" })
            .then(function (res) {
                if (res.ok) {
                    agentProjects = agentProjects.filter(function (p) { return p.id !== projId; });
                    if (currentProject && currentProject.id === projId) {
                        currentProject = agentProjects[0] || null;
                    }
                    if (agentProjects.length === 0) {
                        createDefaultProject();
                    } else {
                        renderProjectsList();
                        if (currentProject) selectProject(currentProject);
                    }
                }
            });
    }

    // Modal: New Project
    function openNewProjectModal() {
        if (projectNameInput) projectNameInput.value = "";
        if (projectDescInput) projectDescInput.value = "";
        if (newProjectError) newProjectError.style.display = "none";
        if (newProjectModal) newProjectModal.style.display = "flex";
        if (projectNameInput) projectNameInput.focus();
    }

    function closeNewProjectModal() {
        if (newProjectModal) newProjectModal.style.display = "none";
    }

    function submitNewProject() {
        var name = projectNameInput ? projectNameInput.value.trim() : "";
        var desc = projectDescInput ? projectDescInput.value.trim() : "";
        if (!name) {
            if (newProjectError) {
                newProjectError.textContent = "Please enter a project name.";
                newProjectError.style.display = "block";
            }
            return;
        }

        apiFetch(API_BASE + "/api/agent/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, description: desc })
        })
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to create project");
                return res.json();
            })
            .then(function (proj) {
                closeNewProjectModal();
                agentProjects.unshift(proj);
                renderProjectsList();
                selectProject(proj);
            })
            .catch(function (err) {
                if (newProjectError) {
                    newProjectError.textContent = err.message;
                    newProjectError.style.display = "block";
                }
            });
    }

    // Workspace Tree & Files
    function loadWorkspaceTree() {
        if (!currentProject || !currentProject.workspace_id) return;
        apiFetch(API_BASE + "/api/agent/workspaces/" + currentProject.workspace_id + "/tree")
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to load workspace tree");
                return res.json();
            })
            .then(function (tree) {
                currentWorkspaceTree = (tree && tree.tree) ? tree.tree : (tree || []);
                renderFileTree(currentWorkspaceTree);

                // Auto-open first file if none open
                if (!activeFilePath && currentWorkspaceTree.length > 0) {
                    var firstFile = findFirstFile(currentWorkspaceTree);
                    if (firstFile) openFileInEditor(firstFile.path);
                }
            })
            .catch(function (err) {
                console.error("loadWorkspaceTree error:", err);
            });
    }

    function findFirstFile(nodes) {
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].type === "file") return nodes[i];
            if (nodes[i].children && nodes[i].children.length > 0) {
                var found = findFirstFile(nodes[i].children);
                if (found) return found;
            }
        }
        return null;
    }

    function renderFileTree(nodes) {
        if (!agentFileTree) return;
        agentFileTree.innerHTML = "";
        if (!nodes || nodes.length === 0) {
            agentFileTree.innerHTML = '<div class="empty-tree-message">No files in workspace.<br>Run an objective or click + to add a file.</div>';
            return;
        }

        renderTreeNodes(nodes, agentFileTree, 0);
    }

    function renderTreeNodes(nodes, parentEl, depth) {
        nodes.forEach(function (node) {
            var itemEl = document.createElement("div");
            itemEl.className = "tree-node" + (activeFilePath === node.path ? " active" : "");
            itemEl.style.paddingLeft = (depth * 14 + 8) + "px";

            var iconEl = document.createElement("span");
            iconEl.className = "tree-node-icon";

            if (node.type === "directory") {
                iconEl.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>';
            } else {
                iconEl.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
            }

            var labelEl = document.createElement("span");
            labelEl.className = "tree-node-label";
            labelEl.textContent = node.name;

            itemEl.appendChild(iconEl);
            itemEl.appendChild(labelEl);

            if (node.type === "file") {
                itemEl.addEventListener("click", function () {
                    openFileInEditor(node.path);
                });
            }

            parentEl.appendChild(itemEl);

            if (node.type === "directory" && node.children && node.children.length > 0) {
                renderTreeNodes(node.children, parentEl, depth + 1);
            }
        });
    }

    function openFileInEditor(filePath) {
        if (!currentProject || !currentProject.workspace_id) return;
        activeFilePath = filePath;
        if (activeFileName) activeFileName.textContent = filePath.split("/").pop();
        fileIsDirty = false;
        if (fileDirtyIndicator) fileDirtyIndicator.style.display = "none";

        apiFetch(API_BASE + "/api/agent/workspaces/" + currentProject.workspace_id + "/files?path=" + encodeURIComponent(filePath))
            .then(function (res) {
                if (!res.ok) throw new Error("Could not read file");
                return res.json();
            })
            .then(function (data) {
                if (agentCodeEditor) {
                    agentCodeEditor.value = data.content || "";
                }
                if (isPreviewActive) {
                    renderFilePreview();
                }
                updateEditorCursor();
                renderFileTree(currentWorkspaceTree);
            })
            .catch(function (err) {
                console.error("openFileInEditor error:", err);
            });
    }

    function saveCurrentFile() {
        if (!currentProject || !currentProject.workspace_id || !activeFilePath) return;
        var content = agentCodeEditor ? agentCodeEditor.value : "";

        apiFetch(API_BASE + "/api/agent/workspaces/" + currentProject.workspace_id + "/files", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                path: activeFilePath,
                content: content
            })
        })
            .then(function (res) {
                if (!res.ok) throw new Error("Save failed");
                return res.json();
            })
            .then(function () {
                fileIsDirty = false;
                if (fileDirtyIndicator) fileDirtyIndicator.style.display = "none";
                if (isPreviewActive) renderFilePreview(true);
                showNotification("File saved successfully.");
            })
            .catch(function (err) {
                alert("Failed to save file: " + err.message);
            });
    }

    var currentPreviewViewport = "desktop";
    var isPreviewExpanded = false;

    function setEditorMode(mode) {
        if (mode === "preview") {
            isPreviewActive = true;
            if (btnModeCode) btnModeCode.classList.remove("active");
            if (btnModePreview) btnModePreview.classList.add("active");
            if (btnTogglePreview) btnTogglePreview.textContent = "Code";
            if (agentCodeEditor) agentCodeEditor.style.display = "none";
            if (workspacePreviewContainer) workspacePreviewContainer.style.display = "flex";
            renderFilePreview(false);
        } else {
            isPreviewActive = false;
            if (btnModePreview) btnModePreview.classList.remove("active");
            if (btnModeCode) btnModeCode.classList.add("active");
            if (btnTogglePreview) btnTogglePreview.textContent = "Preview";
            if (workspacePreviewContainer) workspacePreviewContainer.style.display = "none";
            if (agentCodeEditor) {
                agentCodeEditor.style.display = "block";
                agentCodeEditor.focus();
            }
        }
    }

    function toggleFilePreview() {
        setEditorMode(isPreviewActive ? "code" : "preview");
    }

    function setPreviewViewport(viewport) {
        currentPreviewViewport = viewport;
        var btnMap = {
            desktop: btnViewportDesktop,
            tablet: btnViewportTablet,
            mobile: btnViewportMobile
        };
        Object.keys(btnMap).forEach(function (key) {
            if (btnMap[key]) {
                if (key === viewport) {
                    btnMap[key].classList.add("active");
                } else {
                    btnMap[key].classList.remove("active");
                }
            }
        });
        if (previewViewportFrame) {
            previewViewportFrame.className = "preview-viewport-frame " + viewport;
        }
        if (previewDimensionBadge) {
            var labels = {
                desktop: "Desktop (100%)",
                tablet: "Tablet (768px)",
                mobile: "Mobile (375x667px)"
            };
            previewDimensionBadge.textContent = labels[viewport] || viewport;
        }
    }

    function toggleExpandPreview() {
        var workspaceBody = document.querySelector(".agent-workspace-body");
        if (!workspaceBody) return;
        isPreviewExpanded = !isPreviewExpanded;
        if (isPreviewExpanded) {
            workspaceBody.classList.add("preview-expanded");
            if (btnExpandPreview) btnExpandPreview.title = "Collapse Preview Pane";
        } else {
            workspaceBody.classList.remove("preview-expanded");
            if (btnExpandPreview) btnExpandPreview.title = "Expand Preview Pane";
        }
    }

    function getPreviewUrl(subpath, forceReload) {
        if (!currentProject || !currentProject.workspace_id) return "";
        var cleanSub = (subpath || "").replace(/^\/+/, "");
        if (!cleanSub) cleanSub = "index.html";
        var url = API_BASE + "/api/agent/workspaces/" + encodeURIComponent(currentProject.workspace_id) + "/preview/" + encodeURI(cleanSub);
        var params = [];
        var token = getAccessToken();
        if (token) params.push("token=" + encodeURIComponent(token));
        if (forceReload) params.push("_t=" + Date.now());
        if (params.length > 0) url += "?" + params.join("&");
        return url;
    }

    function loadPreviewIframe(subpath, forceReload) {
        if (!workspacePreviewIframe) return;
        var url = getPreviewUrl(subpath, forceReload);
        if (!url) return;

        if (previewStatusDot) {
            previewStatusDot.classList.add("loading");
        }
        workspacePreviewIframe.onload = function () {
            if (previewStatusDot) {
                previewStatusDot.classList.remove("loading");
            }
        };
        workspacePreviewIframe.onerror = function () {
            if (previewStatusDot) {
                previewStatusDot.classList.remove("loading");
            }
        };

        if (workspacePreviewIframe.src !== url) {
            workspacePreviewIframe.src = url;
        }
    }

    function refreshPreviewIframe(forceReload) {
        if (btnRefreshPreview) {
            btnRefreshPreview.classList.add("spinning");
            setTimeout(function () {
                if (btnRefreshPreview) btnRefreshPreview.classList.remove("spinning");
            }, 600);
        }
        renderFilePreview(forceReload !== false);
    }

    function popoutPreview() {
        var hasIndex = (currentWorkspaceTree || []).some(function (n) {
            return n.name === "index.html" || n.path === "index.html";
        });
        var ext = (activeFilePath || "").split(".").pop().toLowerCase();
        var targetPath = (ext === "html" || ext === "htm") ? activeFilePath : (hasIndex ? "index.html" : (activeFilePath || ""));
        var url = getPreviewUrl(targetPath, false);
        if (url) {
            window.open(url, "_blank");
        }
    }

    function renderFilePreview(forceReload) {
        if (!agentCodeEditor) return;
        var content = agentCodeEditor.value || "";
        var ext = (activeFilePath || "").split(".").pop().toLowerCase();
        var hasIndexHtml = (currentWorkspaceTree || []).some(function (n) {
            return n.name === "index.html" || n.path === "index.html";
        });

        // 1. Static Web Application (HTML or CSS/JS when index.html exists)
        if (ext === "html" || ext === "htm" || ((ext === "css" || ext === "js") && hasIndexHtml) || (!activeFilePath && hasIndexHtml)) {
            if (previewViewportFrame) previewViewportFrame.style.display = "flex";
            if (artifactPreviewPane) artifactPreviewPane.style.display = "none";
            var targetSub = (ext === "html" || ext === "htm") ? activeFilePath : "index.html";
            if (previewAddressText) {
                previewAddressText.textContent = "/" + targetSub + ((ext === "css" || ext === "js") ? " (" + activeFilePath + ")" : "");
            }
            loadPreviewIframe(targetSub, forceReload);
            return;
        }

        // 2. Markdown Viewer
        if (ext === "md" || ext === "markdown") {
            if (previewViewportFrame) previewViewportFrame.style.display = "none";
            if (artifactPreviewPane) {
                artifactPreviewPane.style.display = "block";
                if (previewAddressText) previewAddressText.textContent = "/" + (activeFilePath || "Document.md");
                if (window.marked && window.DOMPurify) {
                    artifactPreviewPane.innerHTML = window.DOMPurify.sanitize(window.marked.parse(content));
                } else {
                    artifactPreviewPane.textContent = content;
                }
            }
            return;
        }

        // 3. JSON Viewer
        if (ext === "json") {
            if (previewViewportFrame) previewViewportFrame.style.display = "none";
            if (artifactPreviewPane) {
                artifactPreviewPane.style.display = "block";
                if (previewAddressText) previewAddressText.textContent = "/" + (activeFilePath || "data.json");
                try {
                    var parsed = JSON.parse(content);
                    artifactPreviewPane.innerHTML = "<div style='padding: 8px;'><pre style='background:#121214;padding:16px;border-radius:8px;border:1px solid #27272a;overflow:auto;'><code style='color:#38bdf8;font-size:12px;font-family:ui-monospace,monospace;'>" + escapeHtml(JSON.stringify(parsed, null, 2)) + "</code></pre></div>";
                } catch (e) {
                    artifactPreviewPane.innerHTML = "<pre><code>" + escapeHtml(content) + "</code></pre>";
                }
            }
            return;
        }

        // 4. CSV Viewer
        if (ext === "csv") {
            if (previewViewportFrame) previewViewportFrame.style.display = "none";
            if (artifactPreviewPane) {
                artifactPreviewPane.style.display = "block";
                if (previewAddressText) previewAddressText.textContent = "/" + (activeFilePath || "data.csv");
                var rows = content.trim().split("\n");
                var tableHtml = "<div style='overflow-x:auto;padding:8px;'><table class='preview-csv-table'>";
                rows.forEach(function (row, idx) {
                    var cols = row.split(",");
                    tableHtml += "<tr>";
                    cols.forEach(function (col) {
                        tableHtml += idx === 0 ? "<th>" + escapeHtml(col.trim()) + "</th>" : "<td>" + escapeHtml(col.trim()) + "</td>";
                    });
                    tableHtml += "</tr>";
                });
                tableHtml += "</table></div>";
                artifactPreviewPane.innerHTML = tableHtml;
            }
            return;
        }

        // 5. Image Viewer
        if (["png", "jpg", "jpeg", "gif", "svg", "webp", "ico"].indexOf(ext) !== -1) {
            if (previewViewportFrame) previewViewportFrame.style.display = "none";
            if (artifactPreviewPane) {
                artifactPreviewPane.style.display = "block";
                if (previewAddressText) previewAddressText.textContent = "/" + activeFilePath;
                var imgUrl = getPreviewUrl(activeFilePath, forceReload);
                artifactPreviewPane.innerHTML = '<div class="preview-image-container"><img src="' + imgUrl + '" alt="' + escapeHtml(activeFilePath) + '" /><div class="preview-image-meta">' + escapeHtml(activeFilePath) + '</div></div>';
            }
            return;
        }

        // 6. Backend Service Notice
        if (["py", "sh", "dockerfile"].indexOf(ext) !== -1 || (activeFilePath && activeFilePath.toLowerCase().indexOf("requirements") !== -1)) {
            if (hasIndexHtml) {
                if (previewViewportFrame) previewViewportFrame.style.display = "flex";
                if (artifactPreviewPane) artifactPreviewPane.style.display = "none";
                if (previewAddressText) previewAddressText.textContent = "/index.html";
                loadPreviewIframe("index.html", forceReload);
            } else {
                if (previewViewportFrame) previewViewportFrame.style.display = "none";
                if (artifactPreviewPane) {
                    artifactPreviewPane.style.display = "block";
                    if (previewAddressText) previewAddressText.textContent = "/" + activeFilePath;
                    artifactPreviewPane.innerHTML = '<div class="preview-backend-card">' +
                        '<div class="backend-icon">⚡</div>' +
                        '<h3>Backend Service Detected</h3>' +
                        '<p>This project contains executable server-side code (<strong>' + escapeHtml(activeFilePath) + '</strong>). Agent Co produces complete source code ready to run locally, in Docker, or deploy to cloud hosting.</p>' +
                        '<div class="backend-actions">' +
                        '<button type="button" class="btn-xs btn-primary" id="btnPreviewDownloadZip">Download Project ZIP</button>' +
                        '<button type="button" class="btn-xs btn-secondary" id="btnPreviewInspectCode">Inspect Source Code</button>' +
                        '</div></div>';
                    var btnDl = document.getElementById("btnPreviewDownloadZip");
                    if (btnDl) btnDl.addEventListener("click", downloadWorkspaceZip);
                    var btnCd = document.getElementById("btnPreviewInspectCode");
                    if (btnCd) btnCd.addEventListener("click", function () { setEditorMode("code"); });
                }
            }
            return;
        }

        // 7. Fallback Code / Text
        if (hasIndexHtml) {
            if (previewViewportFrame) previewViewportFrame.style.display = "flex";
            if (artifactPreviewPane) artifactPreviewPane.style.display = "none";
            if (previewAddressText) previewAddressText.textContent = "/index.html";
            loadPreviewIframe("index.html", forceReload);
        } else {
            if (previewViewportFrame) previewViewportFrame.style.display = "none";
            if (artifactPreviewPane) {
                artifactPreviewPane.style.display = "block";
                if (previewAddressText) previewAddressText.textContent = "/" + (activeFilePath || "Output");
                artifactPreviewPane.innerHTML = "<pre><code>" + escapeHtml(content) + "</code></pre>";
            }
        }
    }

    // Expose helpers globally for testing and inline interactions
    window.setEditorMode = setEditorMode;
    window.downloadWorkspaceZip = downloadWorkspaceZip;
    window.renderFilePreview = renderFilePreview;
    window.setPreviewViewport = setPreviewViewport;

    // Modal: New File
    function openNewFileModal() {
        if (newFileNameInput) newFileNameInput.value = "";
        if (newFileError) newFileError.style.display = "none";
        if (newFileModal) newFileModal.style.display = "flex";
        if (newFileNameInput) newFileNameInput.focus();
    }

    function closeNewFileModal() {
        if (newFileModal) newFileModal.style.display = "none";
    }

    function submitNewFile() {
        var filePath = newFileNameInput ? newFileNameInput.value.trim() : "";
        if (!filePath) {
            if (newFileError) {
                newFileError.textContent = "Please enter a file path.";
                newFileError.style.display = "block";
            }
            return;
        }
        if (!currentProject || !currentProject.workspace_id) return;

        apiFetch(API_BASE + "/api/agent/workspaces/" + currentProject.workspace_id + "/files", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                path: filePath,
                content: "# " + filePath.split("/").pop() + "\n\n"
            })
        })
            .then(function (res) {
                if (!res.ok) throw new Error("Could not create file");
                return res.json();
            })
            .then(function () {
                closeNewFileModal();
                loadWorkspaceTree();
                openFileInEditor(filePath);
            })
            .catch(function (err) {
                if (newFileError) {
                    newFileError.textContent = err.message;
                    newFileError.style.display = "block";
                }
            });
    }

    function downloadWorkspaceZip() {
        if (!currentProject || !currentProject.workspace_id) return;
        var url = API_BASE + "/api/agent/workspaces/" + currentProject.workspace_id + "/zip";
        var token = getAccessToken();

        apiFetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error("Failed to download ZIP");
                return res.blob();
            })
            .then(function (blob) {
                var blobUrl = window.URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = blobUrl;
                a.download = (currentProject.name || "workspace").replace(/\s+/g, "_") + ".zip";
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(blobUrl);
            })
            .catch(function (err) {
                alert("Download failed: " + err.message);
            });
    }

    // Agent Control Panel Tabs & Helpers
    function switchControlTab(tab) {
        if (tabBtnGraph) tabBtnGraph.classList.toggle("active", tab === "graph");
        if (tabBtnAudit) tabBtnAudit.classList.toggle("active", tab === "audit");
        if (tabBtnPrompts) tabBtnPrompts.classList.toggle("active", tab === "prompts");

        if (controlTabGraph) controlTabGraph.style.display = tab === "graph" ? "flex" : "none";
        if (controlTabAudit) controlTabAudit.style.display = tab === "audit" ? "flex" : "none";
        if (controlTabPrompts) controlTabPrompts.style.display = tab === "prompts" ? "flex" : "none";
    }

    function updateEditorCursor() {
        if (!agentCodeEditor || !editorCursorPosition) return;
        var val = agentCodeEditor.value.substring(0, agentCodeEditor.selectionStart);
        var lines = val.split("\n");
        var line = lines.length;
        var col = lines[lines.length - 1].length + 1;
        editorCursorPosition.textContent = "Ln " + line + ", Col " + col;
    }

    function resetPipelineNodes() {
        ["Planner", "Architect", "Coder"].forEach(function (name) {
            var el = document.getElementById("node" + name);
            var statusEl = document.getElementById("status" + name);
            if (el) el.className = "pipeline-node";
            if (statusEl) statusEl.textContent = "idle";
        });
    }

    function setNodeStatus(name, status) {
        var key = name.charAt(0).toUpperCase() + name.slice(1).toLowerCase();
        var el = document.getElementById("node" + key);
        var statusEl = document.getElementById("status" + key);
        if (el) {
            el.className = "pipeline-node " + status;
        }
        if (statusEl) {
            statusEl.textContent = status;
        }
    }

    // Antigravity-Style Activity Feed Engine
    var currentActionPlanSteps = [];
    var currentCompletedStepIndex = 0;
    var SENSITIVE_KEY_REGEX = /(?:api[_-]?key|token|secret|password|auth(?:orization)?|credential|private[_-]?key)/i;
    var SENSITIVE_VAL_REGEX = /(?:gsk_[a-zA-Z0-9_-]{20,}|sk-[a-zA-Z0-9_-]{20,}|Bearer\s+[a-zA-Z0-9._-]{20,})/gi;

    function formatActivityDuration(ms) {
        if (ms === null || ms === undefined || ms < 0) return "";
        if (ms < 1000) return Math.round(ms) + " ms";
        var sec = ms / 1000;
        return (sec < 10 ? sec.toFixed(1) : Math.round(sec)) + " s";
    }

    function sanitizeSafeValue(val) {
        if (typeof val === "string") {
            return val.replace(SENSITIVE_VAL_REGEX, "[REDACTED]");
        }
        if (Array.isArray(val)) {
            return val.map(sanitizeSafeValue);
        }
        if (val && typeof val === "object") {
            return sanitizeSafeArgs(val);
        }
        return val;
    }

    function sanitizeSafeArgs(args) {
        if (!args || typeof args !== "object") return args;
        var sanitized = {};
        for (var k in args) {
            if (Object.prototype.hasOwnProperty.call(args, k)) {
                if (SENSITIVE_KEY_REGEX.test(k)) {
                    sanitized[k] = "[REDACTED]";
                } else {
                    sanitized[k] = sanitizeSafeValue(args[k]);
                }
            }
        }
        return sanitized;
    }

    function getFilenameFromPath(p) {
        if (!p || typeof p !== "string") return "file";
        var parts = p.trim().replace(/\\/g, "/").split("/");
        return parts.filter(Boolean).pop() || p;
    }

    function formatToolActionTitle(toolName, args, status, retryCount) {
        var isFailed = status === "failed" || status === "error";
        var isRunning = status === "running";
        var filename = args ? getFilenameFromPath(args.path || args.file_path) : "file";

        switch (toolName) {
            case "write_file":
                if (retryCount > 0 && isRunning) return { title: "Retrying " + filename + " (attempt " + (retryCount + 1) + ")", subtitle: args ? args.path : "" };
                if (isFailed) return { title: "Writing " + filename + " · Failed", subtitle: args ? args.path : "" };
                if (isRunning) return { title: "Writing " + filename, subtitle: args ? args.path : "" };
                return { title: "Wrote " + filename, subtitle: args ? args.path : "" };

            case "read_file":
                if (isFailed) return { title: "Reading " + filename + " · Failed", subtitle: args ? args.path : "" };
                if (isRunning) return { title: "Reading " + filename, subtitle: args ? args.path : "" };
                return { title: "Read " + filename, subtitle: args ? args.path : "" };

            case "list_files":
            case "list_directory":
                var dir = args && args.path ? args.path : "";
                if (dir && dir !== "." && dir !== "/") {
                    var dirName = getFilenameFromPath(dir);
                    return { title: (isRunning ? "Inspecting " : "Inspected ") + dirName + " directory" };
                }
                return { title: isRunning ? "Inspecting workspace files" : "Inspected workspace files" };

            case "web_search":
                var q = args ? (args.query || args.q || "") : "";
                var qShort = q.length > 36 ? (q.slice(0, 33) + "...") : q;
                var qText = qShort ? (' for "' + qShort + '"') : "";
                if (isFailed) return { title: "Searching web" + qText + " · Failed" };
                return { title: (isRunning ? "Searching web" : "Searched web") + qText };

            case "fetch_url_content":
                var url = args ? (args.url || "") : "";
                var host = url;
                try {
                    if (url.indexOf("http") === 0) {
                        var parsed = new URL(url);
                        host = parsed.hostname;
                    }
                } catch (e) {
                    host = url.slice(0, 30);
                }
                return { title: (isRunning ? "Fetching " : "Fetched ") + host };

            case "get_github_repo_metadata":
                var repo = args ? (args.repo || args.repository || "") : "";
                return { title: (isRunning ? "Inspecting GitHub repo " : "Inspected GitHub repo ") + repo };

            case "run_command":
            case "bash":
            case "execute_command":
                var cmd = args ? (args.command || args.cmd || "") : "";
                var shortCmd = cmd.length > 32 ? (cmd.slice(0, 29) + "...") : cmd;
                if (isFailed) return { title: "Command failed: " + shortCmd };
                return { title: (isRunning ? "Running " : "Ran ") + shortCmd };

            default:
                var clean = toolName.replace(/_/g, " ");
                var capitalized = clean.charAt(0).toUpperCase() + clean.slice(1);
                if (isFailed) return { title: capitalized + " · Failed" };
                return { title: (isRunning ? "Running " : "Completed ") + clean };
        }
    }

    function getActivityIconSvg(type, toolName, status) {
        if (status === "failed" || status === "error") {
            return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
        }
        if (type === "plan") {
            return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>';
        }
        if (type === "verification") {
            return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>';
        }
        if (toolName === "write_file") {
            return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><polyline points="10 13 8 15 10 17"/><polyline points="14 17 16 15 14 13"/></svg>';
        }
        if (toolName === "web_search" || toolName === "fetch_url_content") {
            return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';
        }
        if (toolName === "read_file" || (toolName && toolName.indexOf("file") !== -1)) {
            return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>';
        }
        return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';
    }

    function renderAntigravityActivityItem(item) {
        if (!streamingLogsConsole) return;
        var placeholder = streamingLogsConsole.querySelector(".log-system");
        if (placeholder) placeholder.remove();

        var container = streamingLogsConsole.querySelector(".antigravity-activity-list");
        if (!container) {
            container = document.createElement("div");
            container.className = "antigravity-activity-list";
            var ongoing = streamingLogsConsole.querySelector(".antigravity-ongoing-indicator");
            if (ongoing) {
                streamingLogsConsole.insertBefore(container, ongoing);
            } else {
                streamingLogsConsole.appendChild(container);
            }
        }

        var itemEl = document.createElement("div");
        itemEl.className = "antigravity-activity-item" + (item.status === "failed" ? " is-failed" : "");

        var row = document.createElement("div");
        row.className = "antigravity-activity-row";

        var left = document.createElement("div");
        left.className = "antigravity-activity-left";

        var icon = document.createElement("div");
        icon.className = "antigravity-activity-icon";
        icon.innerHTML = getActivityIconSvg(item.type, item.toolName, item.status);
        left.appendChild(icon);

        var text = document.createElement("div");
        text.className = "antigravity-activity-text";

        var title = document.createElement("div");
        title.className = "antigravity-activity-title" + (item.status === "failed" ? " status-failed" : "");
        title.textContent = item.title;
        text.appendChild(title);

        if (item.subtitle && item.title.indexOf(item.subtitle) === -1) {
            var sub = document.createElement("div");
            sub.className = "antigravity-activity-subtitle";
            sub.textContent = item.subtitle;
            text.appendChild(sub);
        }
        left.appendChild(text);
        row.appendChild(left);

        var right = document.createElement("div");
        right.className = "antigravity-activity-right";

        if (item.retryCount && item.retryCount > 0) {
            var retryBadge = document.createElement("span");
            retryBadge.className = "antigravity-retry-badge";
            retryBadge.textContent = "Retry " + item.retryCount;
            right.appendChild(retryBadge);
        }

        var chevron = document.createElement("span");
        chevron.className = "antigravity-activity-chevron";
        chevron.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>';
        right.appendChild(chevron);
        row.appendChild(right);
        itemEl.appendChild(row);

        // Drawer
        var hasDetails = Boolean(item.inputArgs || item.toolResult || item.error || item.stepId || item.toolName || item.verificationCriteria);
        if (hasDetails) {
            var drawer = document.createElement("div");
            drawer.className = "antigravity-activity-drawer";
            drawer.style.display = "none";

            var chips = document.createElement("div");
            chips.className = "antigravity-activity-chips";
            if (item.toolName) {
                var c1 = document.createElement("span");
                c1.className = "antigravity-activity-chip";
                c1.textContent = "tool: " + item.toolName;
                chips.appendChild(c1);
            }
            if (item.stepId) {
                var c2 = document.createElement("span");
                c2.textContent = "step: " + item.stepId;
                chips.appendChild(c2);
            }
            if (item.durationMs) {
                var c3 = document.createElement("span");
                c3.textContent = "duration: " + formatActivityDuration(item.durationMs);
                chips.appendChild(c3);
            }
            if (item.retryCount) {
                var c4 = document.createElement("span");
                c4.textContent = "attempt: " + (item.retryCount + 1);
                chips.appendChild(c4);
            }
            drawer.appendChild(chips);

            if (item.error) {
                var errDiv = document.createElement("div");
                errDiv.style.cssText = "color: #f87171; background: rgba(239,68,68,0.15); padding: 5px 8px; border-radius: 4px; word-break: break-word;";
                errDiv.innerHTML = "<strong>Error:</strong> " + escapeHtml(item.error);
                drawer.appendChild(errDiv);
            }

            if (item.verificationCriteria && item.verificationCriteria.length > 0) {
                var critDiv = document.createElement("div");
                critDiv.style.cssText = "display: flex; flex-direction: column; gap: 3px; color: #9ca3af;";
                var critLabel = document.createElement("strong");
                critLabel.textContent = "Criteria Evaluated:";
                critDiv.appendChild(critLabel);
                item.verificationCriteria.forEach(function (c) {
                    var cRow = document.createElement("div");
                    cRow.style.cssText = "display: flex; align-items: center; gap: 6px; color: #d1d5db;";
                    cRow.innerHTML = '<span style="color: #34d399;">✓</span><span>' + escapeHtml(c) + '</span>';
                    critDiv.appendChild(cRow);
                });
                drawer.appendChild(critDiv);
            }

            if (item.inputArgs && Object.keys(item.inputArgs).length > 0) {
                var safeArgs = sanitizeSafeArgs(item.inputArgs);
                var argsPre = document.createElement("pre");
                argsPre.className = "antigravity-activity-pre";
                argsPre.textContent = JSON.stringify(safeArgs, null, 2);
                drawer.appendChild(argsPre);
            }

            if (item.toolResult !== undefined && item.toolResult !== null) {
                var resPre = document.createElement("pre");
                resPre.className = "antigravity-activity-pre";
                resPre.textContent = typeof item.toolResult === "object" ? JSON.stringify(item.toolResult, null, 2) : String(item.toolResult);
                drawer.appendChild(resPre);
            }

            itemEl.appendChild(drawer);

            row.addEventListener("click", function () {
                var isExpanded = drawer.style.display !== "none";
                drawer.style.display = isExpanded ? "none" : "flex";
                if (isExpanded) {
                    itemEl.classList.remove("is-expanded");
                } else {
                    itemEl.classList.add("is-expanded");
                }
            });
        }

        container.appendChild(itemEl);
        streamingLogsConsole.scrollTop = streamingLogsConsole.scrollHeight;
    }

    function updateOngoingIndicator(text) {
        if (!streamingLogsConsole) return;
        var existing = streamingLogsConsole.querySelector(".antigravity-ongoing-indicator");
        if (!text) {
            if (existing) existing.remove();
            return;
        }
        if (!existing) {
            existing = document.createElement("div");
            existing.className = "antigravity-ongoing-indicator";
            existing.innerHTML = '<div class="antigravity-ongoing-spinner"></div><span class="antigravity-ongoing-label"></span>';
            streamingLogsConsole.appendChild(existing);
        }
        var label = existing.querySelector(".antigravity-ongoing-label");
        if (label) label.textContent = text;
        streamingLogsConsole.scrollTop = streamingLogsConsole.scrollHeight;
    }

    function appendStreamingLog(message, level) {
        if (!streamingLogsConsole) return;
        level = level || "info";
        var line = document.createElement("div");
        line.className = "log-line log-" + level;
        line.textContent = "[" + new Date().toLocaleTimeString() + "] " + message;
        streamingLogsConsole.appendChild(line);
        streamingLogsConsole.scrollTop = streamingLogsConsole.scrollHeight;
    }

    function clearStreamingLogs() {
        if (streamingLogsConsole) {
            streamingLogsConsole.innerHTML = '<div class="log-line log-system">Workspace initialized. Ready to execute objectives.</div>';
        }
    }

    function addAuditCard(record) {
        if (!auditTrailList) return;
        var emptyEl = auditTrailList.querySelector(".audit-empty-state");
        if (emptyEl) emptyEl.remove();

        auditActionRecords.push(record);
        if (auditActionsCount) auditActionsCount.textContent = auditActionRecords.length + " action(s) executed";

        var card = document.createElement("div");
        card.className = "audit-card";

        var header = document.createElement("div");
        header.className = "audit-card-header";

        var titleDiv = document.createElement("div");
        titleDiv.className = "audit-card-title";
        titleDiv.innerHTML = '<span class="audit-step-badge">' + escapeHtml(record.step_id || "step") + '</span><span>' + escapeHtml(record.tool_name || "tool") + '</span>';

        var metaDiv = document.createElement("div");
        metaDiv.className = "audit-card-meta";
        var statusClass = record.status === "success" ? "status-success" : "status-error";
        metaDiv.innerHTML = '<span class="audit-status-tag ' + statusClass + '">' + escapeHtml(record.status || "done") + '</span><span class="audit-duration">' + (record.duration_ms || 0) + 'ms</span>';

        header.appendChild(titleDiv);
        header.appendChild(metaDiv);

        var body = document.createElement("div");
        body.className = "audit-card-body";
        body.style.display = "none";

        // Arguments
        var argsSec = document.createElement("div");
        argsSec.className = "audit-section";
        argsSec.innerHTML = '<label>Input Arguments</label><pre class="audit-pre">' + escapeHtml(JSON.stringify(record.tool_args || {}, null, 2)) + '</pre>';
        body.appendChild(argsSec);

        // Result
        var resSec = document.createElement("div");
        resSec.className = "audit-section";
        var resPreview = typeof record.tool_result === "object" ? JSON.stringify(record.tool_result, null, 2) : String(record.tool_result || "");
        resSec.innerHTML = '<label>Tool Result</label><pre class="audit-pre">' + escapeHtml(resPreview) + '</pre>';
        body.appendChild(resSec);

        // Citations / Evidence
        if (record.tool_result && typeof record.tool_result === "object" && record.tool_result.evidence_url) {
            var citSec = document.createElement("div");
            citSec.className = "audit-section";
            citSec.innerHTML = '<label>Source Citation</label><a href="' + escapeHtml(record.tool_result.evidence_url) + '" target="_blank" rel="noopener noreferrer" style="color: #60a5fa; font-size: 11px;">' + escapeHtml(record.tool_result.evidence_url) + '</a>';
            body.appendChild(citSec);
        }

        header.addEventListener("click", function () {
            body.style.display = body.style.display === "none" ? "flex" : "none";
        });

        card.appendChild(header);
        card.appendChild(body);
        auditTrailList.appendChild(card);
    }

    // Execute Objective via Server-Sent Events (SSE)
    function runAgentObjective() {
        if (agentIsRunning) return;
        var objective = agentObjectiveInput ? agentObjectiveInput.value.trim() : "";
        if (!objective) {
            alert("Please enter an objective for the agent.");
            return;
        }
        if (!currentProject || !currentProject.workspace_id) {
            alert("Please select or create a project first.");
            return;
        }

        var taskType = agentTaskTypeSelect ? agentTaskTypeSelect.value : "general";

        agentIsRunning = true;
        if (btnRunAgent) btnRunAgent.disabled = true;
        if (runBtnText) runBtnText.textContent = "Executing...";

        if (agentStatusBadges) agentStatusBadges.style.display = "flex";
        if (badgeExecution) {
            badgeExecution.className = "agent-badge badge-running";
            badgeExecution.textContent = "EXEC: RUNNING";
        }
        if (badgeDeliverable) badgeDeliverable.textContent = "DELIVERABLE: -";
        if (badgeVerification) badgeVerification.textContent = "VERIFICATION: -";
        if (badgeObjective) {
            badgeObjective.className = "agent-badge badge-objective";
            badgeObjective.textContent = "OBJECTIVE: RUNNING";
        }

        switchControlTab("graph");
        resetPipelineNodes();
        setNodeStatus("planner", "running");
        currentActionPlanSteps = [];
        currentCompletedStepIndex = 0;
        clearStreamingLogs();
        updateOngoingIndicator("Planning objective…");

        auditActionRecords = [];
        if (auditTrailList) {
            auditTrailList.innerHTML = '<div class="audit-empty-state">Executing actions...</div>';
        }

        var customKeys = getActiveCustomKeys();
        var payload = {
            objective: objective,
            task_type: taskType
        };
        if (customKeys) {
            payload.custom_keys = customKeys;
        }

        var url = API_BASE + "/api/agent/workspaces/" + currentProject.workspace_id + "/runs";
        var token = getAccessToken();
        var headers = {
            "Content-Type": "application/json"
        };
        if (token) {
            headers["Authorization"] = "Bearer " + token;
        }

        fetch(url, {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                if (!res.ok) throw new Error("Agent run failed to start (" + res.status + ")");
                var reader = res.body.getReader();
                var decoder = new TextDecoder("utf-8");
                var buffer = "";

                function readNext() {
                    return reader.read().then(function (result) {
                        if (result.done) {
                            onRunStreamFinished();
                            return;
                        }

                        buffer += decoder.decode(result.value, { stream: true });
                        var lines = buffer.split("\r\n\r\n");
                        buffer = lines.pop(); // keep remainder

                        lines.forEach(function (chunk) {
                            if (!chunk.trim()) return;
                            var evtMatch = chunk.match(/^event:\s*([^\r\n]+)/m);
                            var dataMatch = chunk.match(/^data:\s*([^\r\n]+)/m);
                            var evtName = evtMatch ? evtMatch[1].trim() : "message";
                            var data = {};
                            if (dataMatch) {
                                try {
                                    data = JSON.parse(dataMatch[1]);
                                } catch (e) {
                                    data = { raw: dataMatch[1] };
                                }
                            }

                            processAgentSSEEvent(evtName, data);
                        });

                        return readNext();
                    });
                }

                return readNext();
            })
            .catch(function (err) {
                console.error("SSE stream error:", err);
                appendStreamingLog("Execution failed: " + err.message, "error");
                if (badgeExecution) {
                    badgeExecution.className = "agent-badge badge-error";
                    badgeExecution.textContent = "EXEC: ERROR";
                }
                if (badgeObjective) {
                    badgeObjective.className = "agent-badge badge-objective badge-error";
                    badgeObjective.textContent = "OBJECTIVE: FAILED";
                }
                onRunStreamFinished();
            });
    }

    function processAgentSSEEvent(evtName, data) {
        if (evtName === "run_started") {
            updateOngoingIndicator("Planning objective…");
        } else if (evtName === "on_node_start") {
            setNodeStatus(data.node || "planner", "running");
            if (data.node === "planner") {
                updateOngoingIndicator("Planning objective…");
            } else if (data.node === "architect") {
                updateOngoingIndicator("Structuring execution plan…");
            } else if (data.node === "coder") {
                updateOngoingIndicator("Executing tools…");
            }
        } else if (evtName === "on_action_plan") {
            setNodeStatus("planner", "done");
            setNodeStatus("architect", "running");
            var steps = data.plan && data.plan.steps ? data.plan.steps : [];
            currentActionPlanSteps = steps;
            currentCompletedStepIndex = 0;
            renderAntigravityActivityItem({
                type: "plan",
                title: "Plan created · " + steps.length + " steps",
                subtitle: data.plan && data.plan.objective ? data.plan.objective : "",
                status: "success",
                inputArgs: { objective: data.plan ? data.plan.objective : "", task_type: data.plan ? data.plan.task_type : "" },
                toolResult: steps
            });
            if (steps.length > 0) {
                var firstStep = steps[0];
                var target = firstStep.tool_args && firstStep.tool_args.path ? getFilenameFromPath(firstStep.tool_args.path) : (firstStep.tool_name || "");
                updateOngoingIndicator("Executing step 1 of " + steps.length + (target ? (": " + target) : "") + "…");
            }
        } else if (evtName === "on_tool_end") {
            setNodeStatus("coder", "running");
            var retryCount = data.execution_record ? (data.execution_record.retry_count || 0) : 0;
            var isOk = data.status === "success";
            var actionTitleObj = formatToolActionTitle(data.tool_name, data.tool_args, isOk ? "success" : "failed", retryCount);
            var durStr = formatActivityDuration(data.duration_ms);
            var fullTitle = isOk && durStr ? (actionTitleObj.title + " · " + durStr) : actionTitleObj.title;

            renderAntigravityActivityItem({
                type: "tool",
                toolName: data.tool_name,
                stepId: data.step_id,
                title: fullTitle,
                subtitle: actionTitleObj.subtitle,
                status: isOk ? "success" : "failed",
                durationMs: data.duration_ms,
                retryCount: retryCount,
                inputArgs: data.tool_args,
                toolResult: data.tool_result,
                error: data.error
            });

            if (data.execution_record) {
                addAuditCard(data.execution_record);
            }

            currentCompletedStepIndex = (currentCompletedStepIndex || 0) + 1;
            if (currentActionPlanSteps && currentActionPlanSteps.length > 0) {
                var total = currentActionPlanSteps.length;
                if (currentCompletedStepIndex < total) {
                    var nextStep = currentActionPlanSteps[currentCompletedStepIndex];
                    var nextTarget = nextStep.tool_args && nextStep.tool_args.path ? getFilenameFromPath(nextStep.tool_args.path) : (nextStep.tool_name || "");
                    updateOngoingIndicator("Executing step " + (currentCompletedStepIndex + 1) + " of " + total + (nextTarget ? (": " + nextTarget) : "") + "…");
                } else {
                    updateOngoingIndicator("Verifying deliverables…");
                }
            }
        } else if (evtName === "on_node_end") {
            setNodeStatus(data.node || "planner", "done");
            if (data.node === "architect") {
                setNodeStatus("coder", "running");
            }
        } else if (evtName === "on_verification") {
            setNodeStatus("coder", "done");
            updateOngoingIndicator("Verifying deliverables…");
            var vStatus = data.objective_status || "SUCCESS";
            var criteria = data.verification && data.verification.criteria_evaluated ? data.verification.criteria_evaluated : [];
            var cCount = criteria.length;
            var verifTitle = vStatus === "SUCCESS"
                ? ("Verification passed" + (cCount > 0 ? (" · " + cCount + " checks") : ""))
                : (vStatus === "PARTIAL_SUCCESS"
                    ? ("Verification partial" + (cCount > 0 ? (" · " + cCount + " checks") : ""))
                    : "Verification failed");

            renderAntigravityActivityItem({
                type: "verification",
                title: verifTitle,
                subtitle: data.verification && data.verification.evidence_summary ? data.verification.evidence_summary : "",
                status: vStatus === "SUCCESS" ? "success" : "failed",
                toolResult: data.verification,
                verificationCriteria: criteria
            });

            if (data.verification) {
                if (badgeDeliverable) {
                    var dStatus = data.verification.deliverable_status || "-";
                    badgeDeliverable.textContent = "DELIVERABLE: " + dStatus;
                    badgeDeliverable.className = "agent-badge " + (dStatus === "SUCCESS" ? "badge-success" : (dStatus === "PARTIAL_SUCCESS" ? "badge-partial" : (dStatus === "FAILED" ? "badge-error" : "")));
                }
                if (badgeVerification) {
                    var vStatusVal = data.verification.functional_verification_status || data.verification.source_verification_status || "-";
                    if (data.verification.deliverable_status === "FAILED" && vStatusVal === "SUCCESS") {
                        vStatusVal = "FAILED";
                    }
                    badgeVerification.textContent = "VERIFICATION: " + vStatusVal;
                    badgeVerification.className = "agent-badge " + (vStatusVal === "SUCCESS" ? "badge-success" : (vStatusVal === "PARTIAL_SUCCESS" ? "badge-partial" : (vStatusVal === "FAILED" ? "badge-error" : "")));
                }
            }
        } else if (evtName === "run_complete") {
            setNodeStatus("planner", "done");
            setNodeStatus("architect", "done");
            setNodeStatus("coder", "done");
            updateOngoingIndicator(null); // Clean stop upon complete!

            var status = data.objective_status || "SUCCESS";
            var totalDur = formatActivityDuration(data.duration_ms || (data.details && data.details.run_duration_ms));
            renderAntigravityActivityItem({
                type: "status",
                title: status === "SUCCESS" ? ("Objective succeeded" + (totalDur ? (" · " + totalDur) : "")) : ("Objective " + status),
                subtitle: data.final_summary || "",
                status: status === "SUCCESS" ? "success" : "failed"
            });

            if (badgeExecution) {
                var execStatus = data.verification && data.verification.execution_status ? data.verification.execution_status : "SUCCESS";
                badgeExecution.textContent = "EXEC: " + (execStatus === "SUCCESS" ? "DONE" : execStatus);
                badgeExecution.className = "agent-badge " + (execStatus === "SUCCESS" ? "badge-success" : (execStatus === "PARTIAL_SUCCESS" ? "badge-partial" : "badge-error"));
            }
            if (badgeObjective) {
                badgeObjective.textContent = "OBJECTIVE: " + status;
                badgeObjective.className = "agent-badge badge-objective " + (status === "SUCCESS" ? "badge-success" : (status === "PARTIAL_SUCCESS" ? "badge-partial" : "badge-error"));
            }
            if (data.verification) {
                if (badgeDeliverable) {
                    var dStatus = data.verification.deliverable_status || "-";
                    badgeDeliverable.textContent = "DELIVERABLE: " + dStatus;
                    badgeDeliverable.className = "agent-badge " + (dStatus === "SUCCESS" ? "badge-success" : (dStatus === "PARTIAL_SUCCESS" ? "badge-partial" : (dStatus === "FAILED" ? "badge-error" : "")));
                }
                if (badgeVerification) {
                    var vStatus = data.verification.functional_verification_status || data.verification.source_verification_status || "-";
                    if ((data.verification.deliverable_status === "FAILED" || status === "FAILED") && vStatus === "SUCCESS") {
                        vStatus = "FAILED";
                    }
                    badgeVerification.textContent = "VERIFICATION: " + vStatus;
                    badgeVerification.className = "agent-badge " + (vStatus === "SUCCESS" ? "badge-success" : (vStatus === "PARTIAL_SUCCESS" ? "badge-partial" : (vStatus === "FAILED" ? "badge-error" : "")));
                }
            }

            // Refresh tree to show generated files and open primary preview
            loadWorkspaceTree();
            setTimeout(function () {
                var candidate = currentWorkspaceTree.find(function (n) {
                    return n.name === "index.html" || n.name.indexOf("comparison") !== -1 || n.name.indexOf("report") !== -1 || n.name.endsWith(".md") || n.name.endsWith(".py");
                });
                if (candidate) {
                    openFileInEditor(candidate.path);
                    if ((candidate.name === "index.html" || candidate.name.endsWith(".md")) && !isPreviewActive) {
                        setEditorMode("preview");
                    } else if (isPreviewActive) {
                        renderFilePreview(true);
                    }
                } else if (isPreviewActive) {
                    renderFilePreview(true);
                }
            }, 600);
        } else if (evtName === "run_error" || evtName === "error") {
            updateOngoingIndicator(null);
            renderAntigravityActivityItem({
                type: "error",
                title: data.message || data.error || "Execution error",
                subtitle: data.hint || "",
                status: "failed",
                error: data.message || data.error
            });
            if (badgeExecution) {
                badgeExecution.className = "agent-badge badge-error";
                badgeExecution.textContent = "EXEC: ERROR";
            }
            if (badgeObjective) {
                badgeObjective.className = "agent-badge badge-objective badge-error";
                badgeObjective.textContent = "OBJECTIVE: FAILED";
            }
        }
    }

    function onRunStreamFinished() {
        agentIsRunning = false;
        updateOngoingIndicator(null);
        if (btnRunAgent) btnRunAgent.disabled = false;
        if (runBtnText) runBtnText.textContent = "Run Objective";
    }

    // ==========================================================
    // Custom API Keys & External Providers Module
    // ==========================================================
    var RORAK_CUSTOM_KEYS_STORAGE = "rorak_custom_api_keys";
    var activeCustomKeyProvider = "default";

    function getCustomKeys() {
        try {
            var raw = localStorage.getItem(RORAK_CUSTOM_KEYS_STORAGE);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function saveCustomKeys(keysObj) {
        if (!keysObj || keysObj.provider === "default") {
            localStorage.removeItem(RORAK_CUSTOM_KEYS_STORAGE);
        } else {
            localStorage.setItem(RORAK_CUSTOM_KEYS_STORAGE, JSON.stringify(keysObj));
        }
        updateCustomKeyUI();
    }

    function getActiveCustomKeys() {
        var keys = getCustomKeys();
        if (!keys || keys.provider === "default") return null;
        return keys;
    }

    function updateCustomKeyUI() {
        var keys = getActiveCustomKeys();
        var hasActiveCustom = !!keys;

        var sidebarDot = document.getElementById("sidebarKeyStatusDot");
        var agentDot = document.getElementById("agentKeyStatusDot");
        if (sidebarDot) sidebarDot.style.display = hasActiveCustom ? "inline-block" : "none";
        if (agentDot) agentDot.style.display = hasActiveCustom ? "inline-block" : "none";

        var sidebarBtn = document.getElementById("sidebarCustomKeysBtn");
        var agentBtn = document.getElementById("btnAgentCustomKeys");
        var chatBtn = document.getElementById("btnChatCustomKeys");
        var provLabel = hasActiveCustom && keys.provider ? keys.provider.toUpperCase() : "DEFAULT";

        if (sidebarBtn) {
            sidebarBtn.title = hasActiveCustom ? ("Custom Key Active (" + provLabel + ")") : "External APIs & Custom Keys";
        }
        if (agentBtn) {
            agentBtn.title = hasActiveCustom ? ("Custom Key Active (" + provLabel + ")") : "Configure Custom API Keys";
        }
        if (chatBtn) {
            chatBtn.title = hasActiveCustom ? ("Custom Key Active (" + provLabel + ")") : "Configure Custom API Keys";
        }
    }

    function showCustomKeysModal() {
        var modal = document.getElementById("customKeysModal");
        if (!modal) return;
        var saved = getCustomKeys();
        populateCustomKeysForm(saved);
        selectKeyProviderTab(saved && saved.provider ? saved.provider : "default");
        hideKeyValidationStatus();
        fetchServerKeyStatus();
        modal.style.display = "flex";
    }

    function hideCustomKeysModal() {
        var modal = document.getElementById("customKeysModal");
        if (modal) modal.style.display = "none";
        hideKeyValidationStatus();
    }

    function selectKeyProviderTab(provider) {
        activeCustomKeyProvider = provider || "default";

        var tabs = document.querySelectorAll(".key-provider-tab");
        tabs.forEach(function (tab) {
            if (tab.getAttribute("data-provider") === activeCustomKeyProvider) {
                tab.classList.add("active");
            } else {
                tab.classList.remove("active");
            }
        });

        var panels = {
            "default": document.getElementById("panelKeyDefault"),
            "groq": document.getElementById("panelKeyGroq"),
            "openai": document.getElementById("panelKeyOpenAI"),
            "custom": document.getElementById("panelKeyCustom")
        };

        for (var p in panels) {
            if (panels[p]) {
                panels[p].style.display = (p === activeCustomKeyProvider) ? "block" : "none";
            }
        }
        hideKeyValidationStatus();
    }

    function populateCustomKeysForm(config) {
        var inputGroqKey = document.getElementById("inputGroqApiKey");
        var inputGroqModel = document.getElementById("inputGroqModel");
        var inputOpenAIKey = document.getElementById("inputOpenAIApiKey");
        var inputOpenAIModel = document.getElementById("inputOpenAIModel");
        var inputCustomUrl = document.getElementById("inputCustomBaseUrl");
        var inputCustomKey = document.getElementById("inputCustomApiKey");
        var inputCustomModel = document.getElementById("inputCustomModelName");
        var inputTavilyKey = document.getElementById("inputTavilyApiKey");

        if (!config) {
            if (inputGroqKey) inputGroqKey.value = "";
            if (inputGroqModel) inputGroqModel.value = "llama-3.3-70b-versatile";
            if (inputOpenAIKey) inputOpenAIKey.value = "";
            if (inputOpenAIModel) inputOpenAIModel.value = "gpt-4o-mini";
            if (inputCustomUrl) inputCustomUrl.value = "";
            if (inputCustomKey) inputCustomKey.value = "";
            if (inputCustomModel) inputCustomModel.value = "";
            if (inputTavilyKey) inputTavilyKey.value = "";
            return;
        }

        if (inputGroqKey) inputGroqKey.value = config.groq_api_key || (config.provider === "groq" ? config.api_key : "") || "";
        if (inputGroqModel && config.groq_model) inputGroqModel.value = config.groq_model;
        if (inputOpenAIKey) inputOpenAIKey.value = config.openai_api_key || (config.provider === "openai" ? config.api_key : "") || "";
        if (inputOpenAIModel && config.openai_model) inputOpenAIModel.value = config.openai_model;
        if (inputCustomUrl) inputCustomUrl.value = config.base_url || config.custom_base_url || "";
        if (inputCustomKey) inputCustomKey.value = config.custom_api_key || (config.provider === "custom" ? config.api_key : "") || "";
        if (inputCustomModel) inputCustomModel.value = config.model || config.custom_model || "";
        if (inputTavilyKey) inputTavilyKey.value = config.tavily_api_key || "";
    }

    function collectCustomKeysFromForm() {
        var inputGroqKey = document.getElementById("inputGroqApiKey");
        var inputGroqModel = document.getElementById("inputGroqModel");
        var inputOpenAIKey = document.getElementById("inputOpenAIApiKey");
        var inputOpenAIModel = document.getElementById("inputOpenAIModel");
        var inputCustomUrl = document.getElementById("inputCustomBaseUrl");
        var inputCustomKey = document.getElementById("inputCustomApiKey");
        var inputCustomModel = document.getElementById("inputCustomModelName");
        var inputTavilyKey = document.getElementById("inputTavilyApiKey");

        var config = {
            provider: activeCustomKeyProvider,
            tavily_api_key: inputTavilyKey ? inputTavilyKey.value.trim() : ""
        };

        if (activeCustomKeyProvider === "groq") {
            config.groq_api_key = inputGroqKey ? inputGroqKey.value.trim() : "";
            config.api_key = config.groq_api_key;
            config.groq_model = inputGroqModel ? inputGroqModel.value : "llama-3.3-70b-versatile";
            config.model = config.groq_model;
        } else if (activeCustomKeyProvider === "openai") {
            config.openai_api_key = inputOpenAIKey ? inputOpenAIKey.value.trim() : "";
            config.api_key = config.openai_api_key;
            config.openai_model = inputOpenAIModel ? inputOpenAIModel.value : "gpt-4o-mini";
            config.model = config.openai_model;
        } else if (activeCustomKeyProvider === "custom") {
            config.base_url = inputCustomUrl ? inputCustomUrl.value.trim() : "";
            config.custom_base_url = config.base_url;
            config.custom_api_key = inputCustomKey ? inputCustomKey.value.trim() : "";
            config.api_key = config.custom_api_key;
            config.model = inputCustomModel ? inputCustomModel.value.trim() : "default";
            config.custom_model = config.model;
        }

        return config;
    }

    function showKeyValidationStatus(msg, statusType) {
        var banner = document.getElementById("customKeysTestResult");
        if (!banner) return;
        banner.style.display = "block";
        banner.className = "key-validation-status status-" + statusType;
        banner.textContent = msg;
    }

    function hideKeyValidationStatus() {
        var banner = document.getElementById("customKeysTestResult");
        if (banner) {
            banner.style.display = "none";
            banner.textContent = "";
        }
    }

    function testCustomKeyConnection() {
        var config = collectCustomKeysFromForm();
        if (config.provider === "default") {
            showKeyValidationStatus("Default provider uses server environment credentials. No test needed.", "success");
            return;
        }

        var testPayload = {
            provider: config.provider,
            api_key: config.api_key || "",
            base_url: config.base_url || null,
            model: config.model || null
        };

        showKeyValidationStatus("Testing connection to " + config.provider.toUpperCase() + " API...", "loading");

        fetch(API_BASE + "/api/settings/validate-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(testPayload)
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.valid) {
                    showKeyValidationStatus("Success: " + data.message, "success");
                } else {
                    showKeyValidationStatus("Connection Error: " + (data.error || data.message), "error");
                }
            })
            .catch(function (err) {
                showKeyValidationStatus("Validation request failed: " + err.message, "error");
            });
    }

    function fetchServerKeyStatus() {
        var statusEl = document.getElementById("serverConfigStatusText");
        fetch(API_BASE + "/api/settings/keys-status")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (statusEl) {
                    if (data.server_groq_configured) {
                        statusEl.textContent = "Server Groq API Key Active (" + (data.default_model || "Configured") + ")";
                    } else {
                        statusEl.textContent = "Server key not configured. Please supply a custom key.";
                    }
                }
            })
            .catch(function () {});
    }

    function initCustomKeys() {
        updateCustomKeyUI();

        var sidebarBtn = document.getElementById("sidebarCustomKeysBtn");
        var agentBtn = document.getElementById("btnAgentCustomKeys");
        var chatBtn = document.getElementById("btnChatCustomKeys");
        var modal = document.getElementById("customKeysModal");
        var closeBtn = document.getElementById("customKeysCloseBtn");
        var resetBtn = document.getElementById("btnCustomKeysReset");
        var testBtn = document.getElementById("btnCustomKeysTest");
        var saveBtn = document.getElementById("btnCustomKeysSave");

        if (sidebarBtn) sidebarBtn.addEventListener("click", showCustomKeysModal);
        if (agentBtn) agentBtn.addEventListener("click", showCustomKeysModal);
        if (chatBtn) chatBtn.addEventListener("click", showCustomKeysModal);
        if (closeBtn) closeBtn.addEventListener("click", hideCustomKeysModal);

        if (modal) {
            modal.addEventListener("click", function (e) {
                if (e.target === modal) hideCustomKeysModal();
            });
        }

        var tabs = document.querySelectorAll(".key-provider-tab");
        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                var prov = tab.getAttribute("data-provider");
                selectKeyProviderTab(prov);
            });
        });

        var toggles = [
            { btn: "toggleGroqKeyVisibility", input: "inputGroqApiKey" },
            { btn: "toggleOpenAIKeyVisibility", input: "inputOpenAIApiKey" },
            { btn: "toggleCustomKeyVisibility", input: "inputCustomApiKey" },
            { btn: "toggleTavilyKeyVisibility", input: "inputTavilyApiKey" }
        ];

        toggles.forEach(function (t) {
            var b = document.getElementById(t.btn);
            var inp = document.getElementById(t.input);
            if (b && inp) {
                b.addEventListener("click", function () {
                    togglePasswordVisibility(inp, b);
                });
            }
        });

        if (resetBtn) {
            resetBtn.addEventListener("click", function () {
                saveCustomKeys(null);
                populateCustomKeysForm(null);
                selectKeyProviderTab("default");
                showKeyValidationStatus("Reset to default server environment key.", "success");
                showNotification("Custom API keys cleared. Using default server key.", "info");
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener("click", function () {
                var config = collectCustomKeysFromForm();
                saveCustomKeys(config);
                showNotification("Custom key configuration saved and activated!", "success");
                hideCustomKeysModal();
            });
        }

        if (testBtn) {
            testBtn.addEventListener("click", function () {
                testCustomKeyConnection();
            });
        }
    }


    // ── Start on Load ──
    document.addEventListener("DOMContentLoaded", init);

})();
