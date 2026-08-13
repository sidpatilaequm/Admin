/**
 * Organization Module - Reusable JS Logic
 * Handles CRUD operations for Countries, Currencies, Companies, and Channels.
 * Uses real API endpoints via Django proxy.
 */

const OrganizationManager = {
    allCountries: [],
    allCurrencies: [],
    data: {},

    // Toast Notification Helper
    showToast: function (message, type = 'success') {
        console.log(`[${type.toUpperCase()}] ${message}`);

        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.style.position = 'fixed';
            toastContainer.style.top = '20px';
            toastContainer.style.right = '20px';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement('div');
        toast.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
        toast.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(toast);
            bsAlert.close();
        }, 3000);
    },

    // CRUD Logic using Real API
    fetchData: function (module) {
        const loadingEl = document.getElementById('loading');
        const tableEl = document.getElementById('organization-table-container');
        const noDataEl = document.getElementById('no-data');

        if (loadingEl) loadingEl.style.display = 'block';
        if (tableEl) tableEl.style.display = 'none';
        if (noDataEl) noDataEl.style.display = 'none';

        return fetch(`/api/organization/${module}/`)
            .then(response => response.json())
            .then(response => {
                if (loadingEl) loadingEl.style.display = 'none';

                // Typical Java API response structure: { status, statusMsg, data: { module: [...] } }
                let results = [];
                if (response.data && response.data[module]) {
                    results = response.data[module];
                } else if (Array.isArray(response.data)) {
                    results = response.data;
                } else if (Array.isArray(response)) {
                    results = response;
                }

                if (results.length > 0) {
                    if (tableEl) tableEl.style.display = 'block';
                    return results;
                } else {
                    if (noDataEl) noDataEl.style.display = 'block';
                    return [];
                }
            })
            .catch(err => {
                console.error(`Error fetching ${module}:`, err);
                if (loadingEl) loadingEl.style.display = 'none';
                if (noDataEl) noDataEl.style.display = 'block';
                this.showToast(`Failed to load ${module}`, 'error');
                return [];
            });
    },

    saveRecord: function (module, record) {
        if (!this.validate(module, record)) {
            return Promise.reject('Validation failed');
        }

        const id = record.id;
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/organization/${module}/${id}/` : `/api/organization/${module}/`;

        return fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken')
            },
            body: JSON.stringify(record)
        })
            .then(response => response.json().then(data => ({ data, ok: response.ok })))
            .then(({ data, ok }) => {
                if (data.status === '200' || data.status === 'SUCCESS' || data.success || ok) {
                    this.showToast(`${module.slice(0, -1).charAt(0).toUpperCase() + module.slice(0, -1).slice(1)} saved successfully!`);
                    return { success: true };
                } else {
                    throw new Error(data.statusMsg || 'Save failed');
                }
            })
            .catch(err => {
                console.error(`Error saving ${module}:`, err);
                this.showToast(err.message || `Failed to save ${module}`, 'error');
                throw err;
            });
    },

    deleteRecord: function (module, id) {
        if (!confirm("Are you sure you want to delete this?")) {
            return Promise.resolve({ success: false });
        }

        return fetch(`/api/organization/${module}/${id}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': this.getCookie('csrftoken')
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === '200' || data.success) {
                    this.showToast(`${module.slice(0, -1).charAt(0).toUpperCase() + module.slice(0, -1).slice(1)} deleted successfully!`);
                    return { success: true };
                } else {
                    throw new Error(data.statusMsg || 'Delete failed');
                }
            })
            .catch(err => {
                console.error(`Error deleting ${module}:`, err);
                this.showToast(err.message || `Failed to delete ${module}`, 'error');
                throw err;
            });
    },

    fetchCountryData: function () {
        if (this.allCountries.length > 0) return Promise.resolve(this.allCountries);

        return fetch('https://restcountries.com/v3.1/all?fields=name,cca2,idd')
            .then(response => response.json())
            .then(data => {
                this.allCountries = data.map(c => ({
                    name: c.name.common,
                    isoCode: c.cca2,
                    phoneCode: (c.idd.root || '') + (c.idd.suffixes ? c.idd.suffixes[0] : '')
                })).sort((a, b) => a.name.localeCompare(b.name));
                return this.allCountries;
            })
            .catch(err => {
                console.error("Error fetching country names:", err);
                return [];
            });
    },

    fetchCurrencyData: function () {
        if (this.allCurrencies.length > 0) return Promise.resolve(this.allCurrencies);

        return fetch('https://restcountries.com/v3.1/all?fields=currencies')
            .then(response => response.json())
            .then(data => {
                const currencyMap = new Map();
                data.forEach(country => {
                    if (country.currencies) {
                        Object.entries(country.currencies).forEach(([code, details]) => {
                            if (!currencyMap.has(code)) {
                                currencyMap.set(code, {
                                    code: code,
                                    name: details.name,
                                    symbol: details.symbol
                                });
                            }
                        });
                    }
                });
                this.allCurrencies = Array.from(currencyMap.values()).sort((a, b) => a.code.localeCompare(b.code));
                return this.allCurrencies;
            })
            .catch(err => {
                console.error("Error fetching currencies:", err);
                return [];
            });
    },

    autoPopulateCurrencyDetails: function (currencyCode) {
        const currency = this.allCurrencies.find(c => c.code === currencyCode);
        if (currency) {
            const nameInput = document.querySelector('input[name="name"]');
            const symbolInput = document.querySelector('input[name="symbol"]');
            if (nameInput) nameInput.value = currency.name || '';
            if (symbolInput) symbolInput.value = currency.symbol || '';
        }
    },

    autoPopulateCountryDetails: function (countryName) {
        const country = this.allCountries.find(c => c.name === countryName);
        if (country) {
            const isoCodeInput = document.querySelector('input[name="isoCode"]');
            const phoneCodeInput = document.querySelector('input[name="phoneCode"]');
            if (isoCodeInput) isoCodeInput.value = country.isoCode || '';
            if (phoneCodeInput) phoneCodeInput.value = country.phoneCode || '';
        }
    },

    validate: function (module, record) {
        if (module === 'countries' && !record.countryName && !record.name) {
            this.showToast("Country Name is required", "error");
            return false;
        }
        if (module === 'currencies' && !record.currencyCode && !record.code) {
            this.showToast("Currency Code is required", "error");
            return false;
        }
        if (module === 'companies' && !record.companyName && !record.name) {
            this.showToast("Company Name is required", "error");
            return false;
        }
        if (module === 'channels' && !record.channelName && !record.name) {
            this.showToast("Channel Name is required", "error");
            return false;
        }
        return true;
    },

    prefillModal: function (modalId, record) {
        const modal = document.getElementById(modalId);
        const inputs = modal.querySelectorAll('input, select');
        inputs.forEach(input => {
            const name = input.name;
            if (record[name] !== undefined) {
                input.value = record[name];
            } else if (name === 'countryId' && record.country && record.country.countryId) {
                input.value = record.country.countryId;
            } else if (name === 'currencyId' && record.currency && record.currency.currencyId) {
                input.value = record.currency.currencyId;
            }
        });
    },

    getCookie: function (name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
};

window.OrganizationManager = OrganizationManager;
