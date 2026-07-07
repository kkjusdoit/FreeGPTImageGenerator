const { createApp } = Vue;

function normalizeBooleanLike(value, defaultValue = false) {
    if (value === true || value === false) {
        return value;
    }
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (['1', 'true', 'yes', 'on'].includes(normalized)) {
            return true;
        }
        if (['0', 'false', 'no', 'off', ''].includes(normalized)) {
            return false;
        }
    }
    if (typeof value === 'number') {
        return value !== 0;
    }
    return defaultValue;
}

createApp({
    data() {
        return {
            appVersion: 'v12.0.3',
            isLoggedIn: !!localStorage.getItem('auth_token'),
            loginPassword: '',
            currentTab: window.location.hash.replace('#', '') || 'accounts',
            isDarkMode: localStorage.getItem('ui_theme_mode') === 'dark',
			showAccountsPlaintext: false,
            isRunning: false,
            tabs: [
                { id: 'accounts', name: '账号库存', icon: '📦' },
                { id: 'cloud', name: '配额管理', icon: '☁️' },
                { id: 'mailboxes', name: '微软邮箱库', icon: '📬' },
                { id: 'relay', name: '维护设置', icon: '🛠️' },
                { id: 'console', name: '维护日志', icon: '💻' },
            ],
			isDeletingAccounts: false,
            logs: [],
            logBuffer: [],
            logFlushTimer: null,
            config: null,
            accounts: [],
            selectedAccounts: [],
            accountFilter: 'credential',
            showImportAccountModal: false,
            importAccountText: '',
            isImportingAccounts: false,
            showSessionJsonModal: false,
            sessionJsonText: '',
            isImportingSessionJson: false,
			currentPage: 1,
            pageSize: 10,
            totalAccounts: 0,
            evtSource: null,
            stats: {
                success: 0, failed: 0, retries: 0, total: 0, target: 0,
                pwd_blocked: 0, phone_verify: 0,
                success_rate: '0.0%', elapsed: '0.0s', avg_time: '0.0s', progress_pct: '0%',
                mode: '维护待命'
            },
            statsTimer: null,

            showPwd: {
                login: false, web: false, cf: false, imap: false, 
                free_token: false, free_pass: false,
                cm: false, mc: false, clash: false, cpa: false, sub2api: false,
                cf_key: false, cf_modal_key: false,
                mail_domains: true, cf_email: true, gpt_base: true, imap_user: true,
                free_url: true, cm_url: true, cm_email: true, mc_base: true,
                ai_base: true, cluster_url: true, proxy: true, clash_api: true,
                clash_test: true, tg_token: false, tg_chatid: false, cpa_url: true, sub_url: true,
                cluster_secret: false, hero_key: false, duck_token: false, duck_cookie: false,
                smsbower_key: false,
                luckmail: false,
                temporam: false,
                tmailor_token: false,
                fvia_token: false,
                subUrl: false,
                showMailboxesPlaintext: false,
                db_pass: false,
                master_rt: false
            },

            toasts: [],
            toastId: 0,
            confirmModal: { show: false, message: '', resolve: null },
            updateInfo: { hasUpdate: false, version: '', url: '', changelog: '' },
            sub2apiGroups: [],
            isLoadingSub2APIGroups: false,
            cloudAccounts: [],
            selectedCloud: [],
            cloudFilters: ['sub2api', 'cpa'],
            showCloudPlaintext: false,
            cloudPage: 1,
            cloudPageSize: 10,
            cloudTotal: 0,
            localCheckTimes: {},
            localCloudDetails: {},
            isCloudActionLoading: false,
            showCloudDetailModal: false,
            currentCloudDetail: null,
            nowTimestamp: Math.floor(Date.now() / 1000),
            mailboxes: [],
            selectedMailboxes: [],
            mailboxPage: 1,
            mailboxPageSize: 10,
            totalMailboxes: 0,
            showImportMailboxModal: false,
            importMailboxText: '',
            isImportingMailbox: false,
            outlookAuth: {
                showModal: false,
                mailbox: null,
                currentClientId: '',
                authUrl: '',
                pastedUrl: '',
                isGenerating: false,
                isLoading: false
            },
            BUILTIN_CLIENT_ID: "7feada80-d946-4d06-b134-73afa3524fb7",
            gmail_oauth_mode: {
                master_email: '',
                fission_enable: false,
                fission_mode: 'suffix',
                suffix_mode: 'mystic',
                suffix_len_min: 8,
                suffix_len_max: 12
            },
            cloudStatusFilter: 'all',
            searchAccounts: '',
            searchCloud: '',
            searchMailboxes: '',

        };
    },
    mounted() {
        this.applyTheme();
        if (!this.tabs.some(t => t.id === this.currentTab)) {
            this.currentTab = 'accounts';
        }
        if (this.isLoggedIn) {
            this.initApp();
        }
        window.addEventListener('hashchange', () => {
            const tab = window.location.hash.replace('#', '');
            if (tab && this.tabs.some(t => t.id === tab)) {
                this.switchTab(tab);
            }
        });
        this.timer = setInterval(() => {
            this.nowTimestamp = Math.floor(Date.now() / 1000);
        }, 1000);
    },
    beforeUnmount() {
        if(this.statsTimer) clearInterval(this.statsTimer);
    },
	computed: {
        totalPages() {
            return Math.ceil(this.totalAccounts / this.pageSize) || 1;
        },
        filteredAccounts() {
            let res = this.accounts;
            if (this.searchAccounts) {
                const term = this.searchAccounts.toLowerCase();
                res = res.filter(a => a.email && a.email.toLowerCase().includes(term));
            }
            return res;
        },
        filteredCloud() {
            let res = this.cloudAccounts;
            if (this.searchCloud) {
                const term = this.searchCloud.toLowerCase();
                res = res.filter(a => a.credential && a.credential.toLowerCase().includes(term));
            }
            return res;
        },
        filteredMailboxes() {
            let res = this.mailboxes;
            if (this.searchMailboxes) {
                const term = this.searchMailboxes.toLowerCase();
                res = res.filter(a => a.email && a.email.toLowerCase().includes(term));
            }
            return res;
        },
        cloudTotalPages() {
            return Math.ceil(this.cloudTotal / this.cloudPageSize) || 1;
        },
        mailboxTotalPages() {
            return Math.ceil(this.totalMailboxes / this.mailboxPageSize) || 1;
        }
    },
    methods: {
        applyTheme() {
            const nextMode = this.isDarkMode ? 'dark' : 'light';
            document.body.classList.toggle('theme-dark', this.isDarkMode);
            localStorage.setItem('ui_theme_mode', nextMode);
        },
        toggleTheme() {
            this.isDarkMode = !this.isDarkMode;
            this.applyTheme();
            this.showToast(this.isDarkMode ? '已切换为护眼模式' : '已切换为日间模式', 'info');
        },
        showToast(message, type = 'info') {
            const id = this.toastId++;
            this.toasts.push({ id, message, type });
            setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 3500);
        },

        async customConfirm(message) {
            return new Promise((resolve) => {
                this.confirmModal = { show: true, message, resolve };
            });
        },
        handleConfirm(result) {
            if (this.confirmModal.resolve) this.confirmModal.resolve(result);
            this.confirmModal.show = false;
        },
        async authFetch(url, options = {}) {
            const token = localStorage.getItem('auth_token');
            if (!options.headers) options.headers = {};
            options.headers['Authorization'] = 'Bearer ' + token;
            if (options.body && typeof options.body === 'string') {
                options.headers['Content-Type'] = 'application/json';
            }
            const res = await fetch(url, options);
            if (res.status === 401) {
                this.logout();
                this.showToast("登录状态过期，请重新登录！", "warning");
                throw new Error("Unauthorized");
            }
            return res;
        },

        async handleLogin() {
            if(!this.loginPassword) { this.showToast("请输入密码！", "warning"); return; }
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: this.loginPassword })
                });
                const data = await res.json();
                if (data.status === 'success') {
					this.logs = [];
                    localStorage.setItem('auth_token', data.token); 
                    this.isLoggedIn = true;
                    this.initApp();
                    this.showToast("登录成功，欢迎回来！", "success");
                } else { this.showToast(data.message, "error"); }
            } catch (e) { this.showToast("登录请求失败，请检查后端服务。", "error"); }
        },
        logout() {
            localStorage.removeItem('auth_token');
            this.isLoggedIn = false;
            this.loginPassword = '';
			this.logs = [];
            Object.keys(this.showPwd).forEach(k => this.showPwd[k] = false);
			if(this.evtSource) {
                this.evtSource.close();
                this.evtSource = null;
            }
            if(this.statsTimer) clearInterval(this.statsTimer);
        },
        async initApp() {
            await this.fetchConfig();
            this.initSSE();
            this.fetchAccounts();
            this.fetchCloudAccounts();
            this.fetchMailboxes();
            this.startStatsPolling();
            this.checkUpdate();
        },
        startStatsPolling() {
            if(this.statsTimer) clearTimeout(this.statsTimer);
            this.pollStats();
        },
        async pollStats() {
            if(!this.isLoggedIn) return;
            try {
                const res = await this.authFetch('/api/stats');
                const data = await res.json();
                this.stats = data;
                this.isRunning = data.is_running;
            } catch(e) {

            } finally {
                this.statsTimer = setTimeout(() => {
                    this.pollStats();
                }, 1000);
            }
        },
        async fetchConfig() {
            try {
                const res = await this.authFetch('/api/config');
                this.config = await res.json();
                if (!this.config.tg_bot) {
                    this.config.tg_bot = { enable: false, token: '', chat_id: '' };
                }
                if (!this.config.local_microsoft) {
                    this.config.local_microsoft = {
                        enable_fission: false,
                        pool_fission: false,
                        master_email: '',
                        client_id: '',
                        refresh_token: '',
                        suffix_mode: 'fixed',
                        suffix_len_min: 8,
                        suffix_len_max: 8
                    };
                }


                if (this.config) {
                    if (!this.config.smsbower) {
                        this.config.smsbower = {
                            enabled: false, api_key: '', country: 0, service: 'dr',
                            auto_pick_country: true, verify_on_register: false, reuse_phone: true,
                            max_price: 0.08, min_price: 0.05, min_balance: 10.0, max_tries: 3, poll_timeout_sec: 180
                        };
                    } else {
                        this.config.smsbower.min_price = parseFloat(this.config.smsbower.min_price) || 0.05;
                        this.config.smsbower.enabled = normalizeBooleanLike(this.config.smsbower.enabled, false);
                        this.config.smsbower.auto_pick_country = normalizeBooleanLike(this.config.smsbower.auto_pick_country, true);
                        this.config.smsbower.reuse_phone = normalizeBooleanLike(this.config.smsbower.reuse_phone, true);
                        this.config.smsbower.verify_on_register = normalizeBooleanLike(this.config.smsbower.verify_on_register, false);
                    }

                    if (this.config.hero_sms) {
                        this.config.hero_sms.enabled = normalizeBooleanLike(this.config.hero_sms.enabled, false);
                    }
                }
                if (this.config.local_microsoft.suffix_mode === undefined) {
                    this.config.local_microsoft.suffix_mode = 'fixed';
                }
                if (this.config.local_microsoft.suffix_len_min === undefined) {
                    this.config.local_microsoft.suffix_len_min = 8;
                }
                if (this.config.local_microsoft.suffix_len_max === undefined) {
                    this.config.local_microsoft.suffix_len_max = 8;
                }
                if (this.config.local_microsoft.pool_fission === undefined) {
                    this.config.local_microsoft.pool_fission = false;
                }
                if (!this.config.sub2api_mode) {
                    this.config.sub2api_mode = {};
                }
                if (this.config.sub2api_mode.test_model === undefined) {
                    this.config.sub2api_mode.test_model = 'gpt-5.2';
                }
                if (Array.isArray(this.config.sub2api_mode.default_proxy)) {
                    this.config.sub2api_mode.default_proxy = this.config.sub2api_mode.default_proxy.join('\n');
                }
                if (this.config.sub2api_mode.default_proxy === undefined) {
                    this.config.sub2api_mode.default_proxy = '';
                }
                if (!this.config.fvia) {
                    this.config.fvia = { token: '' };
                }
                if (!this.config.tmailor) {
                    this.config.tmailor = { current_token: '' };
                }
                if (!this.config.max_log_lines) {
                    this.config.max_log_lines = 500;
                }
                if (!this.config.temporam) {
                    this.config.temporam = { cookie: '' };
                }
                if (!this.config.tg_bot.template_success) {
                    this.config.tg_bot.template_success = "🎉 <b>注册成功</b>\n⏰ 时间: <code>{time}</code>\n📧 账号: <code>{email}</code>\n🔑 密码: <code>{password}</code>";
                }
                if (!this.config.tg_bot.template_stop) {
                    this.config.tg_bot.template_stop = "🛑 <b>系统已收到停止指令</b>\n\n📊 <b>最终运行统计</b>：\n成功率: {success_rate}% · 成功: {success}/{target} · 失败: {failed} 次 · 风控拦截: {retries} 次 · 密码受阻: {pwd_blocked} 次 · 出现手机: {phone_verify} 次 · 总耗时: {elapsed_time}s · 平均单号: {avg_time}s";
                }
                if (!this.config.database) {
                    this.config.database = {
                        type: 'sqlite',
                        mysql: { host: '127.0.0.1', port: 3306, user: 'root', password: '', db_name: 'wenfxl_manager' }
                    };
                }
                if (!this.config.database.mysql) {
                    this.config.database.mysql = { host: '127.0.0.1', port: 3306, user: 'root', password: '', db_name: 'wenfxl_manager' };
                }
				if (!this.config.sub_domain_level) {
                    this.config.sub_domain_level = 1;
                }
                if (this.config.sub2api_mode.account_concurrency === undefined) {
                    this.config.sub2api_mode.account_concurrency = 10;
                }
                if (this.config.sub2api_mode.account_load_factor === undefined) {
                    this.config.sub2api_mode.account_load_factor = 10;
                }
                if (this.config.sub2api_mode.account_priority === undefined) {
                    this.config.sub2api_mode.account_priority = 1;
                }
                if (this.config.sub2api_mode.account_rate_multiplier === undefined) {
                    this.config.sub2api_mode.account_rate_multiplier = 1.0;
                }
                if (this.config.sub2api_mode.account_group_ids === undefined) {
                    this.config.sub2api_mode.account_group_ids = '';
                }
                if (this.config.sub2api_mode.enable_ws_mode === undefined) {
                    this.config.sub2api_mode.enable_ws_mode = true;
                }
            } catch (e) {}
        },
        async saveConfig() {
            try {
                if (this.config?.sub2api_mode) {
                    this.config.sub2api_mode.default_proxy = String(this.config.sub2api_mode.default_proxy || '')
                        .split(/\r?\n/)
                        .map(s => s.trim())
                        .filter(s => s)
                        .join('\n');
                }
                if (this.config.local_microsoft) {
                    const mode = String(this.config.local_microsoft.suffix_mode || 'fixed').toLowerCase();
                    this.config.local_microsoft.suffix_mode = ['fixed', 'range', 'mystic'].includes(mode) ? mode : 'fixed';

                    let minLen = parseInt(this.config.local_microsoft.suffix_len_min, 10);
                    let maxLen = parseInt(this.config.local_microsoft.suffix_len_max, 10);
                    if (Number.isNaN(minLen)) minLen = 8;
                    if (Number.isNaN(maxLen)) maxLen = minLen;
                    minLen = Math.max(8, Math.min(32, minLen));
                    maxLen = Math.max(8, Math.min(32, maxLen));
                    if (maxLen < minLen) maxLen = minLen;
                    this.config.local_microsoft.suffix_len_min = minLen;
                    this.config.local_microsoft.suffix_len_max = maxLen;
                }
                const res = await this.authFetch('/api/config', {
                    method: 'POST', body: JSON.stringify(this.config)
                });
                const data = await res.json();
                if(data.status === 'success') {
                    this.showToast(data.message, "success");
                    this.pollStats();
                } else { this.showToast("保存失败：" + data.message, "error"); }
            } catch (e) { this.showToast("保存失败网络异常", "error"); }
        },
		async fetchAccounts(isManual = false) {
            if (isManual) {
                this.currentPage = 1;
            }
            try {
                const url = `/api/accounts?page=${this.currentPage}&page_size=${this.pageSize}&account_filter=${this.accountFilter}`;
                const res = await this.authFetch(url);
                const data = await res.json();
                if(data.status === 'success') {
                    this.accounts = data.data ? data.data : data;
                    if (data.total !== undefined) {
                        this.totalAccounts = data.total;
                    } else {
                        this.totalAccounts = this.accounts.length;
                    }
                    
                    this.selectedAccounts = []; 
                    if (isManual) this.showToast("账号列表已刷新！", "success");
                }
            } catch (e) {
                console.error("获取账号列表失败:", e);
            }
        },
		changePage(newPage) {
            if (!newPage || isNaN(newPage)) newPage = 1;
            newPage = Math.max(1, Math.min(newPage, this.totalPages));
            if (this.currentPage === newPage) {
                this.$forceUpdate(); // 强制刷新非法输入的UI
                return;
            }
            this.currentPage = newPage;
            this.selectedAccounts = []; 
            this.fetchAccounts(false);
        },
		changePageSize() {
            this.currentPage = 1;
            
            this.selectedAccounts = []; 
            
            this.fetchAccounts(false);
        },
        switchTab(tabId) {
            this.currentTab = tabId;
            window.location.hash = tabId;
			if (tabId === 'console') {
				this.pollStats(); 
			}
            if (tabId === 'accounts') {
                this.fetchAccounts();
            }
			if (tabId === 'cloud') {
			    this.fetchCloudAccounts();
			}
            if (tabId === 'mailboxes') {
                this.fetchMailboxes();
            }
        },
        async exportSelectedAccounts() {
            const eligibleAccounts = this.eligibleSelectedAccounts();
            if (eligibleAccounts.length === 0) {
                this.showToast("请先勾选需要导出的账号", "warning");
                return;
            }

            const emails = eligibleAccounts.map(acc => acc.email);

            try {
                const res = await this.authFetch('/api/accounts/export_selected', {
                    method: 'POST',
                    body: JSON.stringify({ emails: emails })
                });
                const result = await res.json();

                if (result.status === 'success') {
                    const data = result.data;
                    const timestamp = Math.floor(Date.now() / 1000);
                    if (data.length > 1) {
                        const zip = new JSZip();

                        data.forEach((tokenObj, index) => {
                            const accEmail = tokenObj.email || "unknown";
                            const parts = accEmail.split('@');
                            const prefix = parts[0] || "user";
                            const domain = parts[1] || "domain";

                            const filename = `token_${prefix}_${domain}_${timestamp + index}.json`;
                            zip.file(filename, JSON.stringify(tokenObj, null, 4));
                        });

                        const content = await zip.generateAsync({ type: "blob" });
                        const url = window.URL.createObjectURL(content);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `CPA_Batch_Export_${data.length}_${timestamp}.zip`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(url);

                        this.showToast(`🎉 成功打包导出 ${data.length} 个账号的压缩包！`, "success");
                    } else {
                        data.forEach((tokenObj, index) => {
                            setTimeout(() => {
                                const accEmail = tokenObj.email || "unknown";
                                const parts = accEmail.split('@');
                                const prefix = parts[0] || "user";
                                const domain = parts[1] || "domain";

                                const ts = Math.floor(Date.now() / 1000) + index;
                                const filename = `token_${prefix}_${domain}_${ts}.json`;
                                const jsonString = JSON.stringify(tokenObj, null, 4);
                                const blob = new Blob([jsonString], { type: 'application/json;charset=utf-8' });
                                const url = window.URL.createObjectURL(blob);

                                const a = document.createElement('a');
                                a.href = url;
                                a.download = filename;
                                document.body.appendChild(a);
                                a.click();
                                document.body.removeChild(a);
                                window.URL.revokeObjectURL(url);
                            }, index * 300);
                        });
                        this.showToast(`🎉 成功触发 ${data.length} 个独立 Token 文件的下载！`, "success");
                    }

                    this.selectedAccounts = [];
                } else {
                    this.showToast(result.message, "warning");
                }
            } catch (e) {
                console.error(e);
                this.showToast("导出请求失败，请检查网络或 JSZip 是否加载", "error");
            }
        },
        async submitImportAuthorizedAccounts() {
            if (!this.importAccountText.trim()) {
                return this.showToast("请输入授权账号内容", "warning");
            }
            this.isImportingAccounts = true;
            try {
                const res = await this.authFetch('/api/accounts/import_authorized', {
                    method: 'POST',
                    body: JSON.stringify({ raw_text: this.importAccountText })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.showToast(data.message, 'success');
                    this.showImportAccountModal = false;
                    this.importAccountText = '';
                    this.accountFilter = 'all';
                    this.fetchAccounts(true);
                } else {
                    this.showToast(data.message || '导入失败', 'error');
                }
            } catch (error) {
                this.showToast('导入请求异常，请检查后端', 'error');
            } finally {
                this.isImportingAccounts = false;
            }
        },
        async submitImportSessionJson() {
            if (!this.sessionJsonText.trim()) {
                return this.showToast('请粘贴从 chatgpt.com/api/auth/session 复制的 JSON', 'warning');
            }
            this.isImportingSessionJson = true;
            try {
                const res = await this.authFetch('/api/accounts/import_session_json', {
                    method: 'POST',
                    body: JSON.stringify({ raw_text: this.sessionJsonText })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.showToast(data.message, 'success');
                    this.showSessionJsonModal = false;
                    this.sessionJsonText = '';
                    this.accountFilter = 'all';
                    this.fetchAccounts(true);
                } else {
                    this.showToast(data.message || '导入失败', 'error');
                }
            } catch (error) {
                this.showToast('请求异常，请检查后端连接', 'error');
            } finally {
                this.isImportingSessionJson = false;
            }
        },
		maskEmail(email) {
            if (!email) return '';
            const parts = email.split('@');
            if (parts.length !== 2) return '******'; 
            
            const name = parts[0];
            const maskedDomain = '***.***';
            
            if (name.length <= 3) {
                return name + '***@' + maskedDomain;
            }
            return name.substring(0, 3) + '***@' + maskedDomain;
        },
		exportAccountsToTxt() {
			if (this.selectedAccounts.length === 0) return;

			const textContent = this.selectedAccounts
				.map(acc => `${acc.email}----${acc.password}`)
				.join('\n');

			const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			
			const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
			link.download = `accounts_login_${dateStr}.txt`;
			
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
			URL.revokeObjectURL(url);

			this.showToast(`成功导出 ${this.selectedAccounts.length} 个账号到 TXT`, 'success');
		},
		async deleteSelectedAccounts() {
            if (this.selectedAccounts.length === 0) return;

            const confirmed = await this.customConfirm(`⚠️ 危险操作：\n\n确定要彻底删除选中的 ${this.selectedAccounts.length} 个账号吗？\n删除后数据将无法恢复！`);
            if (!confirmed) return;
			this.isDeletingAccounts = true;
            try {
                const emailsToDelete = this.selectedAccounts.map(acc => acc.email);
                
                const res = await this.authFetch('/api/accounts/delete', {
                    method: 'POST',
                    body: JSON.stringify({ emails: emailsToDelete })
                });
                
                const data = await res.json();
                
                if (data.status === 'success') {
                    this.showToast(`成功物理删除 ${emailsToDelete.length} 个账号`, 'success');
                    this.selectedAccounts = [];
                    this.fetchAccounts();
                } else {
                    this.showToast('删除失败: ' + data.message, 'error');
                }
            } catch (error) {
                this.showToast('删除请求异常，请检查后端', 'error');
            } finally {
				this.isDeletingAccounts = false;
			}
        },
        toggleAll(event) {
            if (event.target.checked) this.selectedAccounts = [...this.filteredAccounts];
            else this.selectedAccounts = [];
        },
		async toggleSystem() {
            if (this.isToggling) return;
            this.isToggling = true;
            try {
                if (this.isRunning) {
                    await this.stopTask();
                } else {
                    this.currentTab = 'console';
                    await this.startManualCheck();
                }
            } finally {
                this.isToggling = false;
            }
        },
        async stopTask() {
            try {
                const res = await this.authFetch('/api/stop', { method: 'POST' });
                const data = await res.json();
                this.showToast("任务已停止", "info");
                this.isRunning = false;
                const now = new Date();
                const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false }); // 获取如 14:30:05 格式
                this.logs.push({
                    parsed: true,
                    time: timeStr,
                    level: '系统',
                    text: '🛑 接收到紧急停止指令，引擎已停止运行！',
                    raw: `[${timeStr}] [系统] 🛑 接收到紧急停止指令，引擎已停止运行！`
                });

                this.$nextTick(() => {
                    const container = document.getElementById('terminal-container');
                    if (container) {
                        container.scrollTop = container.scrollHeight;
                    }
                });
                this.pollStats();
            } catch (e) {
                this.showToast("停止请求发送失败", "error");
            }
        },
        eligibleSelectedAccounts() {
            return this.selectedAccounts.filter(acc => acc && acc.cpa_eligible);
        },
        async bulkPushCPA() {
            if (!this.config.cpa_mode.enable) {
                this.showToast("🚫 请先开启 CPA 巡检并填写 API", "warning"); return;
            }
            const eligibleAccounts = this.eligibleSelectedAccounts();
            if (eligibleAccounts.length === 0) {
                this.showToast("当前选中账号里没有可纳入 CPA 的完整凭证账号", "warning");
                return;
            }
            const confirmed = await this.customConfirm(`确定推送到 CPA？`);
            if (!confirmed) return;
            this.currentTab = 'console';
            for (let i = 0; i < eligibleAccounts.length; i++) {
                const acc = eligibleAccounts[i];
                try {
                    await this.authFetch('/api/account/action', {
                        method: 'POST', body: JSON.stringify({ email: acc.email, action: 'push' })
                    });
                } catch (e) {}
                await new Promise(r => setTimeout(r, 500));
            }
            this.showToast(`批量推送完毕！`, "success");
            this.selectedAccounts = []; 
        },
        async bulkPushSub2API() {
            if (!this.config.sub2api_mode.enable) {
                this.showToast("🚫 请先开启 Sub2API 模式并填写参数", "warning"); return;
            }
            const eligibleAccounts = this.eligibleSelectedAccounts();
            if (eligibleAccounts.length === 0) {
                this.showToast("当前选中账号里没有可纳入后续仓管的完整凭证账号", "warning");
                return;
            }
            const confirmed = await this.customConfirm(`确定推送到 Sub2API？`);
            if (!confirmed) return;
            this.currentTab = 'console';
            for (let i = 0; i < eligibleAccounts.length; i++) {
                const acc = eligibleAccounts[i];
                try {
                    await this.authFetch('/api/account/action', {
                        method: 'POST', body: JSON.stringify({ email: acc.email, action: 'push_sub2api' })
                    });
                } catch (e) {}
                await new Promise(r => setTimeout(r, 500));
            }
            this.showToast(`批量推送完毕！`, "success");
            this.selectedAccounts = []; 
        },
        async triggerAccountAction(account, action) {
            if (action === 'push' && !this.config.cpa_mode.enable) {
                this.showToast("🚫 无法推送：请先配置 CPA 参数！", "warning"); return;
            }
            if ((action === 'push' || action === 'push_sub2api') && !account.cpa_eligible) {
                this.showToast("该账号仅注册成功或凭证不完整，已排除出后续 CPA 流程", "warning");
                return;
            }
            this.currentTab = 'console';
            try {
                const res = await this.authFetch('/api/account/action', {
                    method: 'POST', body: JSON.stringify({ email: account.email, action: action })
                });
                const result = await res.json();
                this.showToast(result.message, result.status);
            } catch (e) {}
        },
        setAccountFilter(filter) {
            if (this.accountFilter === filter) return;
            this.accountFilter = filter;
            this.currentPage = 1;
            this.selectedAccounts = [];
            this.fetchAccounts(false);
        },
        async clearLogs() {
            this.logs = []; 
            try { await this.authFetch('/api/logs/clear', { method: 'POST' }); } catch (e) {}
        },
		initSSE() {
            if (this.evtSource) {
                this.evtSource.close();
                this.evtSource = null;
            }
            if (this.logFlushTimer) {
                clearInterval(this.logFlushTimer);
                this.logFlushTimer = null;
            }
            if (this.sseReconnectTimer) {
                clearTimeout(this.sseReconnectTimer);
                this.sseReconnectTimer = null;
            }

            const token = localStorage.getItem('auth_token');
            if (!token) return;
            const timestamp = new Date().getTime();
            const url = `/api/logs/stream?token=${token}&_t=${timestamp}`;

            this.evtSource = new EventSource(url);
            this.logFlushTimer = setInterval(() => {
                if (this.logBuffer.length > 0) {
                    const container = document.getElementById('terminal-container');
                    let isScrolledToBottom = true;
                    if (container) {
                        isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 100;
                    }
                    this.logs.push(...this.logBuffer);
                    this.logBuffer = [];
                    const maxLines = (this.config && this.config.max_log_lines) ? this.config.max_log_lines : 500;
                    if (this.logs.length > maxLines) {
                        this.logs.splice(0, this.logs.length - maxLines);
                    }
                    this.$nextTick(() => {
                        if (container && (isScrolledToBottom || this.logs.length < 20)) {
                            container.scrollTo({
                                top: container.scrollHeight,
                                behavior: 'auto'
                            });
                        }
                    });
                }
            }, 300);

            this.evtSource.onmessage = (event) => {
                let rawText = event.data;
                rawText = rawText.trim();
                if (!rawText) return;

                let logObj = { id: Date.now() + Math.random(), parsed: false, raw: rawText };
                const regex = /^\[(.*?)\]\s*\[(.*?)\]\s+(.*)$/;
                const match = rawText.match(regex);

                if (match) {
                    logObj = {
                        parsed: true,
                        time: match[1],
                        level: match[2].toUpperCase(),
                        text: match[3],
                        raw: rawText
                    };
                }
                this.logBuffer.push(logObj);
            };
            this.evtSource.onerror = (event) => {
                console.error("🔴 SSE 连接断开或异常。");
                if (this.evtSource) {
                    this.evtSource.close();
                    this.evtSource = null;
                }

                if (this.isLoggedIn) {
                    console.log("⏳ 准备在 3 秒后强制重新建立日志通道...");
                    this.sseReconnectTimer = setTimeout(() => {
                        this.initSSE();
                    }, 3000);
                }
            };
        },
        async fetchSub2ApiGroups() {
            if (!this.config || !this.config.sub2api_mode) return;
            if (!this.config.sub2api_mode.api_url || !this.config.sub2api_mode.api_key) {
                this.showToast('Please save the Sub2API URL and API key first.', 'warning');
                return;
            }

            this.isLoadingSub2APIGroups = true;
            try {
                const res = await this.authFetch('/api/sub2api/groups');
                const data = await res.json();
                if (data.status === 'success') {
                    const raw = data.data;
                    let groups = [];
                    if (Array.isArray(raw)) groups = raw;
                    else if (raw && Array.isArray(raw.list)) groups = raw.list;
                    else if (raw && Array.isArray(raw.data)) groups = raw.data;

                    this.sub2apiGroups = groups;
                    if (groups.length === 0) {
                        this.showToast('No Sub2API groups found. Create one in Sub2API first.', 'warning');
                    } else {
                        this.showToast(`Fetched ${groups.length} Sub2API groups.`, 'success');
                    }
                } else {
                    this.showToast(data.message || 'Failed to fetch Sub2API groups.', 'error');
                }
            } catch (e) {
                this.showToast('Group fetch error: ' + e.message, 'error');
            } finally {
                this.isLoadingSub2APIGroups = false;
            }
        },
        isGroupSelected(id) {
            if (!this.config || !this.config.sub2api_mode) return false;
            const ids = String(this.config.sub2api_mode.account_group_ids || '')
                .split(',')
                .map(s => s.trim())
                .filter(s => s);
            return ids.includes(String(id));
        },
        toggleGroup(id) {
            if (!this.config || !this.config.sub2api_mode) return;
            const ids = String(this.config.sub2api_mode.account_group_ids || '')
                .split(',')
                .map(s => s.trim())
                .filter(s => s);
            const value = String(id);
            const index = ids.indexOf(value);
            if (index >= 0) ids.splice(index, 1);
            else ids.push(value);
            this.config.sub2api_mode.account_group_ids = ids.join(',');
        },
        async startManualCheck() {
            if(this.isRunning) {
                this.showToast('请先停止当前运行的任务', 'warning');
                return;
            }
            try {
                const res = await this.authFetch('/api/start_check', {
                    method: 'POST'
                });
                const data = await res.json();

                if(data.code === 200) {
                    this.showToast(data.message, 'success');
                    this.pollStats();
                } else {
                    this.showToast(data.message || '启动测活失败', 'error');
                }
            } catch (err) {
                this.showToast('网络请求异常', 'error');
            }
        },
        async checkUpdate(isManual = false) {
            try {
                const res = await this.authFetch(`/api/system/check_update?current_version=${this.appVersion}`);
                const data = await res.json();

                if (data.status === 'success') {
                    if (data.has_update) {
                        this.updateInfo = {
                            hasUpdate: true,
                            version: data.remote_version,
                            url: data.html_url || data.download_url || 'https://github.com/wenfxl/openai-cpa/releases/latest',
                            changelog: data.changelog
                        };
                        if (isManual) {
                            this.promptUpdate();
                        }
                    } else if (isManual) {
                        this.showToast("当前已是最新版本！", "success");
                    }
                } else {
                    if (isManual) this.showToast(data.message || "检查更新失败", "error");
                }
            } catch (e) {
                if (isManual) this.showToast("检查更新请求失败，请检查网络", "error");
            }
        },
        async promptUpdate() {
            if (!this.updateInfo.hasUpdate) return;
            const msg = `🚀 发现新版本: ${this.updateInfo.version}\n\n📝 更新内容:\n${this.updateInfo.changelog}\n\n是否前往 GitHub 查看并下载更新？`;
            const confirmed = await this.customConfirm(msg);
            if (confirmed) {
                window.open(this.updateInfo.url, '_blank');
            }
        },
        async restartSystem() {
            const confirmed = await this.customConfirm("⚠️ 危险操作：\n\n确定要重启整个后端系统吗？\n如果当前有任务正在运行，将会被强制中断！");
            if (!confirmed) return;

            try {
                this.showToast("🚀 正在向服务器发送重启指令...", "info");
                const res = await this.authFetch('/api/system/restart', { method: 'POST' });
                const data = await res.json();

                if (data.status === 'success') {
                    this.showToast("✅ 系统正在重启，网页将于 6 秒后自动刷新...", "success");
                    if(this.statsTimer) clearInterval(this.statsTimer);
                    if(this.evtSource) this.evtSource.close();

                    setTimeout(() => {
                        window.location.reload();
                    }, 6000);
                } else {
                    this.showToast(data.message || "重启指令发送失败", "error");
                }
            } catch (e) {
                this.showToast("请求异常，请检查后端状态", "error");
            }
        },
        formatTime(dateStr) {
            if (!dateStr) return '-';
            let utcStr = dateStr;
            if (typeof dateStr === 'string' && !dateStr.includes('Z')) {
                utcStr = dateStr.replace(' ', 'T') + 'Z';
            }
            const d = new Date(utcStr);
            if (isNaN(d.getTime())) return dateStr;
            const pad = (n) => n.toString().padStart(2, '0');
            return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
        },
        async exportSub2Api() {
            const eligibleAccounts = this.eligibleSelectedAccounts();
            if (eligibleAccounts.length === 0) {
                this.showToast('请先勾选账号', 'warning');
                return;
            }
            try {
                const emailsToExport = eligibleAccounts.map(item =>
                    typeof item === 'object' ? item.email : item
                );

                const response = await this.authFetch('/api/accounts/export_sub2api', {
                    method: 'POST',
                    body: JSON.stringify({ emails: emailsToExport })
                });
                const res = await response.json();

                if (res.status === 'success') {
                    const accounts = res.data.accounts;
                    const timestamp = Math.floor(Date.now() / 1000);

                    if (accounts.length > 1) {
                        const zip = new JSZip();

                        accounts.forEach((acc, index) => {
                            const prefix = (acc.name || "user").split('@')[0];

                            const singleAccountData = {
                                exported_at: res.data.exported_at,
                                proxies: res.data.proxies,
                                accounts: [acc]
                            };

                            const filename = `sub2api_${prefix}_${timestamp + index}.json`;
                            zip.file(filename, JSON.stringify(singleAccountData, null, 2));
                        });

                        const content = await zip.generateAsync({ type: "blob" });
                        const url = window.URL.createObjectURL(content);
                        const link = document.createElement('a');
                        link.href = url;
                        link.download = `Sub2Api_批量导出_${accounts.length}个_${timestamp}.zip`;
                        document.body.appendChild(link);
                        link.click();
                        link.remove();
                        window.URL.revokeObjectURL(url);

                        this.showToast(`🎉 成功打包并下载 ${accounts.length} 个独立配置文件！`, 'success');
                    } else {
                        const content = JSON.stringify(res.data, null, 2);
                        const blob = new Blob([content], { type: 'application/json' });
                        const url = window.URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = url;
                        link.download = `sub2api_export_${timestamp}.json`;
                        document.body.appendChild(link);
                        link.click();
                        link.remove();
                        window.URL.revokeObjectURL(url);

                        this.showToast(`成功导出 ${accounts.length} 个账号到单个文件`, 'success');
                    }

                    this.selectedAccounts = [];
                } else {
                    this.showToast(res.message || '导出失败', 'error');
                }
            } catch (error) {
                console.error('导出异常:', error);
                this.showToast('导出异常，请检查 JSZip 是否加载', 'error');
            }
        },

        async fetchCloudAccounts() {
            if (this.cloudFilters.length === 0) {
                this.cloudAccounts = [];
                this.cloudTotal = 0;
                return;
            }
            const types = this.cloudFilters.join(',');
            try {
                const res = await this.authFetch(`/api/cloud/accounts?types=${types}&status_filter=${this.cloudStatusFilter}&page=${this.cloudPage}&page_size=${this.cloudPageSize}`);
                const data = await res.json();
                if(data.status === 'success') {
                    this.cloudAccounts = (data.data || []).map(acc => ({
                        ...acc,
                        last_check: this.localCheckTimes[acc.id] || acc.last_check || '-',
                        details: this.localCloudDetails[acc.id] || acc.details || {},
                        _loading: null
                    }));
                    this.cloudTotal = data.total || 0;
                    this.selectedCloud = [];
                } else {
                    this.showToast(data.message, "error");
                }
            } catch (e) {
                console.error(e);
                this.showToast("获取云端数据失败", "error");
            }
        },

        async singleCloudAction(acc, action) {
            if (action === 'delete' && !confirm('⚠️ 危险操作：确认在远端彻底删除该账号吗？')) return;

            const actionName = action === 'check' ? '测活' : (action === 'enable' ? '启用' : (action === 'disable' ? '禁用' : '删除'));
            this.showToast(`正在对账号进行 ${actionName}，请稍候...`, 'info');
            acc._loading = action;

            try {
                const res = await this.authFetch('/api/cloud/action', {
                    method: 'POST',
                    body: JSON.stringify({ accounts: [{id: String(acc.id), type: acc.account_type}], action: action })
                });
                const result = await res.json();
                if (result.updated_details && result.updated_details[acc.id]) {
                    acc.details = result.updated_details[acc.id];
                    this.localCloudDetails[acc.id] = result.updated_details[acc.id];
                }
                if (action === 'enable' && result.status !== 'error') acc.status = 'active';
                if (action === 'disable' && result.status !== 'error') acc.status = 'disabled';

                if (action === 'check') {
                    const now = new Date().toLocaleString('zh-CN', { hour12: false });
                    this.localCheckTimes[acc.id] = now;
                    acc.last_check = now;

                    if (result.status === 'warning') {
                        acc.status = 'disabled';
                    }
                }
                this.showToast(result.message, result.status);

                setTimeout(() => {
                    if (action === 'delete' || action === 'check') {
                        this.fetchCloudAccounts();
                    }
                }, 1500);

            } catch (e) {
                this.showToast("操作异常，请检查网络", "error");
            } finally {
                acc._loading = null;
            }
        },

        async bulkCloudAction(action) {
            if (this.selectedCloud.length === 0) {
                return this.showToast('请先勾选需要操作的账号', 'warning');
            }
            if (action === 'delete' && !confirm(`⚠️ 危险操作：确认删除选中的 ${this.selectedCloud.length} 个账号吗？`)) return;

            const actionName = action === 'check' ? '测活' : (action === 'enable' ? '启用' : (action === 'disable' ? '禁用' : '删除'));
            this.showToast(`正在批量 ${actionName} ${this.selectedCloud.length} 个账号，耗时较长请耐心等待...`, 'info');
            this.isCloudActionLoading = true;

            try {
                const res = await this.authFetch('/api/cloud/action', {
                    method: 'POST',
                    body: JSON.stringify({ accounts: this.selectedCloud, action: action })
                });
                const result = await res.json();
                if (result.updated_details) {
                    this.selectedCloud.forEach(selected => {
                        const targetAcc = this.cloudAccounts.find(a => String(a.id) === String(selected.id) && a.account_type === selected.type);
                        if (result.updated_details) {
                            this.selectedCloud.forEach(selected => {
                                if (result.updated_details[selected.id]) {
                                    this.localCloudDetails[selected.id] = result.updated_details[selected.id]; // 存入缓存
                                }
                            });
                        }
                    });
                }
                if (action === 'check') {
                    const now = new Date().toLocaleString('zh-CN', { hour12: false });
                    this.selectedCloud.forEach(c => { this.localCheckTimes[c.id] = now; });
                }

                this.showToast(result.message, result.status);
                this.fetchCloudAccounts();
                this.selectedCloud = [];
            } catch (e) {
                this.showToast("批量操作异常", "error");
            } finally {
                this.isCloudActionLoading = false;
            }
        },
        toggleAllCloud(e) {
            if (e.target.checked) {
                this.selectedCloud = this.filteredCloud.map(a => ({ id: String(a.id), type: a.account_type }));
            } else {
                this.selectedCloud = [];
            }
        },
        viewCloudDetails(acc) {
            if (!acc.details || Object.keys(acc.details).length === 0) {
                this.showToast("CPA 账号暂无用量缓存，请先点击【测活】拉取！", "warning");
                return;
            }
            this.currentCloudDetail = acc;
            this.showCloudDetailModal = true;
        },
        changeCloudPage(newPage) {
            if (!newPage || isNaN(newPage)) newPage = 1;
            newPage = Math.max(1, Math.min(newPage, this.cloudTotalPages));
            if (this.cloudPage === newPage) {
                this.$forceUpdate();
                return;
            }
            this.cloudPage = newPage;
            this.fetchCloudAccounts();
        },
        changeCloudPageSize() {
            this.cloudPage = 1;
            this.selectedCloud = [];
            this.fetchCloudAccounts();
        },
        formatDuration(seconds) {
            if (!seconds || seconds < 0) return "0s";
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);

            let res = "";
            if (h > 0) res += h + "h ";
            if (m > 0 || h > 0) res += m + "m ";
            res += s + "s";
            return res;
        },
        maskValue(val, type = 'auto') {
            if (!val) return '未配置';
            if (type === 'email' || (type === 'auto' && val.includes('@'))) {
                const parts = val.split('@');
                return parts[0].substring(0, 2) + '***@' + '***';
            }
            if (type === 'url' || (type === 'auto' && val.startsWith('http'))) {
                try {
                    const url = new URL(val);
                    return `${url.protocol}//*****${url.port ? ':'+url.port : ''}${url.pathname.length > 1 ? '/...' : ''}`;
                } catch(e) { return val.substring(0, 8) + '...'; }
            }
            return val.length > 8 ? val.substring(0, 4) + '***' + val.slice(-4) : val.substring(0, 2) + '***';
        },
        async fetchMailboxes(isManual = false) {
            if (isManual) this.mailboxPage = 1;
            try {
                const res = await this.authFetch(`/api/mailboxes?page=${this.mailboxPage}&page_size=${this.mailboxPageSize}`);
                const data = await res.json();
                if(data.status === 'success') {
                    this.mailboxes = data.data;
                    this.totalMailboxes = data.total || this.mailboxes.length;
                    this.selectedMailboxes = [];
                    if (isManual) this.showToast("邮箱库已刷新！", "success");
                }
            } catch (e) {
                console.error("获取邮箱库失败:", e);
            }
        },
        changeMailboxPage(newPage) {
            if (!newPage || isNaN(newPage)) newPage = 1;
            newPage = Math.max(1, Math.min(newPage, this.mailboxTotalPages));
            if (this.mailboxPage === newPage) {
                this.$forceUpdate();
                return;
            }
            this.mailboxPage = newPage;
            this.fetchMailboxes();
        },
        changeMailboxPageSize() {
            this.mailboxPage = 1;
            this.fetchMailboxes();
        },
        toggleAllMailboxes(event) {
            if (event.target.checked) this.selectedMailboxes = [...this.filteredMailboxes];
            else this.selectedMailboxes = [];
        },
        async submitImportMailboxes() {
            if (!this.importMailboxText.trim()) return this.showToast("请输入内容", "warning");
            this.isImportingMailbox = true;
            try {
                const res = await this.authFetch('/api/mailboxes/import', {
                    method: 'POST',
                    body: JSON.stringify({ raw_text: this.importMailboxText })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.showToast(`成功导入 ${data.count} 个邮箱！`, "success");
                    this.showImportMailboxModal = false;
                    this.importMailboxText = '';
                    this.fetchMailboxes(true);
                } else {
                    this.showToast("导入失败: " + data.message, "error");
                }
            } catch (e) {
                this.showToast("导入请求失败", "error");
            } finally {
                this.isImportingMailbox = false;
            }
        },
        async deleteSelectedMailboxes() {
            if (this.selectedMailboxes.length === 0) return;
            const confirmed = await this.customConfirm(`确定要删除选中的 ${this.selectedMailboxes.length} 个邮箱吗？`);
            if (!confirmed) return;

            const idsToDelete = this.selectedMailboxes.map(m => m.id || m.email);
            try {
                const res = await this.authFetch('/api/mailboxes/delete', {
                    method: 'POST',
                    body: JSON.stringify({ ids: idsToDelete })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.showToast("删除成功", "success");
                    this.fetchMailboxes();
                } else {
                    this.showToast("删除失败: " + data.message, "error");
                }
            } catch (e) {
                this.showToast("请求异常", "error");
            }
        },
        openOutlookAuthModal(mailbox) {
            const cid = mailbox.client_id || this.config?.local_microsoft?.client_id || this.BUILTIN_CLIENT_ID;
            if (!cid) {
                this.showToast("🚫 无法获取有效的 Client ID！", "warning");
                return;
            }
            this.outlookAuth.mailbox = mailbox;
            this.outlookAuth.currentClientId = cid;
            this.outlookAuth.authUrl = '';
            this.outlookAuth.pastedUrl = '';
            this.outlookAuth.showModal = true;
        },

        async generateOutlookAuthUrl() {
            this.outlookAuth.isGenerating = true;
            try {
                const res = await this.authFetch('/api/mailboxes/oauth_url', {
                    method: 'POST',
                    body: JSON.stringify({ client_id: this.outlookAuth.currentClientId })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.outlookAuth.authUrl = data.url;
                } else {
                    this.showToast("生成失败: " + data.message, "error");
                }
            } catch (e) {
                this.showToast("网络请求异常", "error");
            } finally {
                this.outlookAuth.isGenerating = false;
            }
        },
        async submitOutlookAuthCode() {
            this.outlookAuth.isLoading = true;
            try {
                const res = await this.authFetch('/api/mailboxes/oauth_exchange', {
                    method: 'POST',
                    body: JSON.stringify({
                        email: this.outlookAuth.mailbox.email,
                        client_id: this.outlookAuth.currentClientId,
                        code_or_url: this.outlookAuth.pastedUrl
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.showToast(data.message, "success");
                    this.outlookAuth.showModal = false;
                    if (this.outlookAuth.mailbox.isFission && data.refresh_token) {
                        this.config.local_microsoft.refresh_token = data.refresh_token;
                        await this.saveConfig();
                        this.showToast("✅ Token 已自动填入并保存！", "success");
                    } else {
                        this.fetchMailboxes();
                    }
                } else {
                    this.showToast("换取失败: " + data.message, "error");
                }
            } catch (e) {
                this.showToast("网络请求异常", "error");
            } finally {
                this.outlookAuth.isLoading = false;
            }
        },
        exportSelectedMailboxesToTxt() {
            if (this.selectedMailboxes.length === 0) {
                this.showToast("请先勾选需要导出的邮箱", "warning");
                return;
            }
            const textContent = this.selectedMailboxes
                .map(m => {
                    const pwd = m.password || '';
                    const cid = m.client_id || '';
                    const rt = m.refresh_token || '';
                    return `${m.email}----${pwd}----${cid}----${rt}`;
                })
                .join('\n');

            const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;

            const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
            link.download = `microsoft_mailboxes_${dateStr}.txt`;

            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);

            this.showToast(`🎉 成功导出 ${this.selectedMailboxes.length} 个邮箱到 TXT`, 'success');
            this.selectedMailboxes = [];
        },
        async recoverSelectedMailboxes() {
            if (this.selectedMailboxes.length === 0) {
                this.showToast("请先勾选需要恢复的邮箱", "warning");
                return;
            }

            const confirmed = await this.customConfirm(`确定要将选中的 ${this.selectedMailboxes.length} 个邮箱状态重置为【正常/闲置】吗？\n(可用于解除死号误标)`);
            if (!confirmed) return;

            const emailsToRecover = this.selectedMailboxes.map(m => m.email);

            try {
                const res = await this.authFetch('/api/mailboxes/update_status', {
                    method: 'POST',
                    body: JSON.stringify({ emails: emailsToRecover, status: 0 })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    this.showToast(data.message, "success");
                    this.selectedMailboxes = [];
                    this.fetchMailboxes();
                } else {
                    this.showToast("恢复失败: " + data.message, "error");
                }
            } catch (e) {
                this.showToast("请求异常", "error");
            }
        },
        async exportAllAccounts() {
            try {
                const res = await this.authFetch('/api/accounts/export_all', { method: 'POST' });
                const data = await res.json();

                if (data.status === 'success') {
                    const allData = data.data;
                    if (allData.length === 0) {
                        this.showToast('账号库是空的，无需导出', 'warning');
                        return;
                    }

                    const zip = new JSZip();
                    const timestamp = Math.floor(Date.now() / 1000);

                    const txtContent = allData.map(acc => `${acc.email}----${acc.password}`).join('\n');
                    zip.file(`accounts_list_${timestamp}.txt`, txtContent);

                    const cpaFolder = zip.folder("cpa");
                    const sub2apiFolder = zip.folder("sub2api");

                    const proxyPool = this.buildSub2ApiProxyPool(this.config?.sub2api_mode?.default_proxy || "");

                    const validAccounts = allData.filter(acc => acc.token_data && acc.token_data.access_token);

                    validAccounts.forEach((acc, index) => {
                        const accEmail = acc.email || "unknown";
                        const parts = accEmail.split('@');
                        const prefix = parts[0] || "user";
                        const domain = parts[1] || "domain";

                        const cpaData = {
                            ...acc.token_data,
                            email: accEmail,
                            password: acc.password
                        };
                        cpaFolder.file(`token_${prefix}_${domain}_${timestamp + index}.json`, JSON.stringify(cpaData, null, 4));

                        const proxyObj = proxyPool.length ? proxyPool[index % proxyPool.length] : null;
                        const accountNode = {
                            name: accEmail.slice(0, 64),
                            platform: "openai",
                            type: "oauth",
                            credentials: { refresh_token: acc.token_data.refresh_token || "" },
                            concurrency: this.config?.sub2api_mode?.account_concurrency || 10,
                            priority: this.config?.sub2api_mode?.account_priority || 1,
                            rate_multiplier: this.config?.sub2api_mode?.account_rate_multiplier || 1.0,
                            extra: { load_factor: this.config?.sub2api_mode?.account_load_factor || 10 }
                        };

                        if (proxyObj) {
                            accountNode.proxy_key = proxyObj.proxy_key;
                        }

                        const sub2apiData = {
                            exported_at: new Date().toISOString(),
                            proxies: proxyObj ? [proxyObj] : [],
                            accounts: [accountNode]
                        };
                        sub2apiFolder.file(`sub2api_${prefix}_${domain}_${timestamp + index}.json`, JSON.stringify(sub2apiData, null, 4));
                    });

                    const content = await zip.generateAsync({ type: "blob" });
                    const url = window.URL.createObjectURL(content);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `OpenAI_Accounts_Bundle_${timestamp}.zip`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);

                    this.showToast(`成功导出 ${allData.length} 个账号，并已自动注入 Sub2API 代理节点！`, 'success');
                } else {
                    this.showToast(data.message || '导出失败', 'error');
                }
            } catch (e) {
                console.error(e);
                this.showToast('导出异常，请检查网络或刷新页面', 'error');
            }
        },

        async clearAllAccounts() {
            const confirmed = await this.customConfirm('⚠️ 危险操作！确定要删除【账号库】中的所有已注册账号吗？此操作不可恢复。');
            if (!confirmed) return;

            try {
                const res = await this.authFetch('/api/accounts/clear_all', { method: 'POST' });
                const data = await res.json();

                if (data.status === 'success') {
                    this.showToast('账号库已全部清空', 'success');
                    this.fetchAccounts();
                } else {
                    this.showToast(data.message, 'error');
                }
            } catch (e) {
                this.showToast('清空异常', 'error');
            }
        },
        async exportAllMailboxes() {
            try {
                const res = await this.authFetch('/api/mailboxes/export_all', { method: 'POST' });
                const data = await res.json();

                if (data.status === 'success') {
                    const allData = data.data;
                    if (allData.length === 0) {
                        this.showToast('邮箱库是空的，无需导出', 'warning');
                        return;
                    }
                    const text = allData.map(m =>
                        `${m.email}----${m.password}----${m.client_id || ''}----${m.refresh_token || ''}`
                    ).join('\n');

                    const blob = new Blob([text], { type: 'text/plain' });
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `Mailboxes_Backup_${new Date().getTime()}.txt`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);

                    this.showToast(`成功导出 ${allData.length} 个邮箱`, 'success');
                } else {
                    this.showToast(data.message || '导出失败', 'error');
                }
            } catch (e) {
                this.showToast('导出异常', 'error');
            }
        },
        async clearAllMailboxes() {
            const confirmed = await this.customConfirm('⚠️ 危险操作！确定要删除【微软邮箱库】中的所有数据吗？');
            if (!confirmed) return;

            try {
                const res = await this.authFetch('/api/mailboxes/clear_all', { method: 'POST' });
                const data = await res.json();

                if (data.status === 'success') {
                    this.showToast('邮箱库已全部清空', 'success');
                    this.fetchMailboxes();
                } else {
                    this.showToast(data.message, 'error');
                }
            } catch (e) {
                this.showToast('清空异常', 'error');
            }
        },
        parseSub2ApiProxy(proxyUrl) {
            if (!proxyUrl) return null;
            try {
                let parseUrl = proxyUrl;
                const originalProtocol = proxyUrl.split('://')[0];
                if (originalProtocol && !['http', 'https', 'socks4', 'socks5'].includes(originalProtocol)) {
                     parseUrl = proxyUrl.replace(originalProtocol + '://', 'http://');
                }

                const url = new URL(parseUrl);
                const protocol = originalProtocol || url.protocol.replace(':', '');
                const host = url.hostname;
                const port = url.port;
                const username = decodeURIComponent(url.username || '');
                const password = decodeURIComponent(url.password || '');

                if (!protocol || !host || !port) return null;

                const proxyKey = `${protocol}|${host}|${port}|${username}|${password}`;
                const proxyDict = {
                    proxy_key: proxyKey,
                    name: "openai-cpa",
                    protocol: protocol,
                    host: host,
                    port: parseInt(port),
                    status: "active"
                };
                if (username && password) {
                    proxyDict.username = username;
                    proxyDict.password = password;
                }
                return proxyDict;
            } catch (e) {
                return null;
            }
        },
        buildSub2ApiProxyPool(rawValue) {
            const rawItems = Array.isArray(rawValue)
                ? rawValue
                : String(rawValue || '').replace(/\r/g, '\n').split('\n');

            const proxyPool = [];
            const seen = new Set();
            rawItems.forEach(item => {
                const value = String(item || '').trim();
                if (!value || seen.has(value)) return;
                seen.add(value);

                const proxyObj = this.parseSub2ApiProxy(value);
                if (proxyObj) {
                    proxyPool.push(proxyObj);
                }
            });
            return proxyPool;
        },
    }
}).mount('#app');
