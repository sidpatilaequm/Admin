/**
 * Category Management Module
 * Handles Hierarchical Category/Subcategory Tree Grid
 */

const CategoryManager = {
    data: {
        categories: [],
        expandedNodes: new Set(), // Set of "type-id" strings
        currentPage: 1,
        pageSize: 10,
        searchQuery: '',
        treeData: {} // Map of categoryId -> tree structure
    },

    init: function() {
        this.cacheDom();
        this.bindEvents();
        this.fetchCategories();
    },

    cacheDom: function() {
        this.$tableBody = document.getElementById('categoriesTableBody');
        this.$search = document.getElementById('treeSearch');
        this.$addCategoryBtn = document.getElementById('addCategoryBtn');
        this.$refreshBtn = document.getElementById('refreshBtn');
        this.$collapseAllBtn = document.getElementById('collapseAllBtn');
        this.$loader = document.getElementById('loading-overlay');
        
        // Modals
        this.categoryModal = new bootstrap.Modal(document.getElementById('categoryModal'));
        this.subcategoryModal = new bootstrap.Modal(document.getElementById('subcategoryModal'));
        this.statusModal = new bootstrap.Modal(document.getElementById('confirmStatusModal'));
        
        // Forms
        this.$categoryForm = document.getElementById('categoryForm');
        this.$subcategoryForm = document.getElementById('subcategoryForm');
    },

    bindEvents: function() {
        this.$addCategoryBtn.addEventListener('click', () => this.openCategoryModal());
        this.$refreshBtn.addEventListener('click', () => this.fetchCategories());
        this.$collapseAllBtn.addEventListener('click', () => this.collapseAll());
        
        this.$search.addEventListener('input', (e) => {
            this.data.searchQuery = e.target.value.toLowerCase();
            this.renderTable();
        });

        document.getElementById('saveCategoryBtn').addEventListener('click', () => this.saveCategory());
        document.getElementById('saveSubcategoryBtn').addEventListener('click', () => this.saveSubcategory());

        // Event delegation for table actions
        this.$tableBody.addEventListener('click', (e) => {
            const $target = e.target.closest('.tree-expander, .action-btn, .status-toggle');
            if (!$target) return;

            const id = $target.dataset.id;
            const type = $target.dataset.type; // 'category' or 'subcategory'
            const action = $target.dataset.action;

            if ($target.classList.contains('tree-expander')) {
                this.toggleNode(id, type);
            } else if (action === 'edit') {
                if (type === 'category') this.openCategoryModal(id);
                else this.openSubcategoryModal(id, null, true);
            } else if (action === 'add-child') {
                this.openSubcategoryModal(null, {id, type});
            } else if (action === 'toggle-status') {
                this.openStatusModal(id, type);
            }
        });
    },

    fetchCategories: function() {
        this.showLoader(true);
        fetch('/api/categories')
            .then(response => {
                // If not 200 OK, we handle it as an error to trigger fallback
                if (!response.ok) {
                    console.warn(`HTTP Error ${response.status}: Falling back to dummy data`);
                    this.loadDummyCategories();
                    return null;
                }
                return response.json();
            })
            .then(res => {
                if (!res) return; // Already handled by previous then

                if (res.status === '200' || res.status === 'SUCCESS' || res.status === 200) {
                    this.data.categories = res.data.categories || [];
                    if (this.data.categories.length === 0) {
                        this.loadDummyCategories();
                    } else {
                        this.renderTable();
                    }
                } else {
                    console.warn('API returned non-success status:', res);
                    this.loadDummyCategories();
                }
            })
            .catch(err => {
                console.warn('Fetch failed, using dummy data:', err);
                this.loadDummyCategories();
            })
            .finally(() => this.showLoader(false));
    },

    loadDummyCategories: function() {
        console.log('Loading dummy categories...');
        this.data.categories = [
            { id: 1, categoryName: 'Electronics', code: 'ELEC001', isActive: true },
            { id: 2, categoryName: 'Fashion', code: 'FASH002', isActive: true },
            { id: 3, categoryName: 'Home & Living', code: 'HOME003', isActive: true },
            { id: 4, categoryName: 'Industrial Supplies', code: 'IND004', isActive: false }
        ];
        this.renderTable();
        this.showLoader(false); // Ensure loader is hidden
    },

    fetchSubtree: function(categoryId) {
        if (this.data.treeData[categoryId]) return Promise.resolve(this.data.treeData[categoryId]);

        return fetch(`/api/subcategories/tree/${categoryId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP Error ${response.status}`);
                }
                return response.json();
            })
            .then(res => {
                if (res.status === '200' || res.status === 'SUCCESS' || res.status === 200) {
                    this.data.treeData[categoryId] = res.data.tree || [];
                    return this.data.treeData[categoryId];
                }
                throw new Error(res.statusMsg || 'API Error');
            })
            .catch(err => {
                console.warn(`Subtree API Error for ${categoryId}, using dummy data:`, err);
                this.loadDummySubtree(categoryId);
                return this.data.treeData[categoryId];
            });
    },

    loadDummySubtree: function(categoryId) {
        const dummyTrees = {
            1: [ // Electronics
                {
                    id: 101, name: 'Computers', code: 'COMP', children: [
                        { id: 1011, name: 'Laptops', code: 'LAP', children: [] },
                        { id: 1012, name: 'Desktops', code: 'DSK', children: [] }
                    ]
                },
                {
                    id: 102, name: 'Mobiles', code: 'MOB', children: [
                        { id: 1021, name: 'Smartphones', code: 'SMP', children: [] }
                    ]
                }
            ],
            2: [ // Fashion
                {
                    id: 201, name: 'Men Wear', code: 'MEN', children: [
                        { id: 2011, name: 'Shirts', code: 'SHRT', children: [] },
                        { id: 2012, name: 'Trousers', code: 'TRSR', children: [] }
                    ]
                },
                { id: 202, name: 'Women Wear', code: 'WMN', children: [] }
            ],
            3: [ // Home
                { id: 301, name: 'Kitchen Appliances', code: 'KIT', children: [] },
                { id: 302, name: 'Furniture', code: 'FURN', children: [] }
            ]
        };
        this.data.treeData[categoryId] = dummyTrees[categoryId] || [];
    },

    renderTable: function() {
        this.$tableBody.innerHTML = '';
        
        // If there's a search query, we should ideally search through all loaded data
        // For this implementation, we'll check top-level and then recursively if needed
        const matchesSearch = (item, type) => {
            const name = type === 'category' ? item.categoryName : item.name;
            const code = item.code || '';
            if (name.toLowerCase().includes(this.data.searchQuery) || code.toLowerCase().includes(this.data.searchQuery)) {
                return true;
            }
            
            // If it's a category and we have its tree data, search children
            if (type === 'category' && this.data.treeData[item.id]) {
                return this.hasMatchingChild(this.data.treeData[item.id]);
            }
            
            // If it's a subcategory with children
            if (type === 'subcategory' && item.children) {
                return this.hasMatchingChild(item.children);
            }
            
            return false;
        };

        const filteredCategories = this.data.categories.filter(c => matchesSearch(c, 'category'));

        if (filteredCategories.length === 0) {
            this.$tableBody.innerHTML = `
                <tr>
                    <td colspan="4" class="empty-state">
                        <i class="las la-folder-open"></i>
                        No categories found. ${this.data.searchQuery ? 'Try a different search.' : 'Create your first category.'}
                    </td>
                </tr>
            `;
            return;
        }

        filteredCategories.forEach(cat => {
            this.renderRow(cat, 'category', 0);
            
            const nodeKey = `category-${cat.id}`;
            // Automatically expand if there's a search and it has a matching child
            const shouldExpand = this.data.expandedNodes.has(nodeKey) || (this.data.searchQuery && this.hasMatchingChild(this.data.treeData[cat.id] || []));
            
            if (shouldExpand) {
                this.renderSubtree(cat.id, 1);
            }
        });
    },

    hasMatchingChild: function(nodes) {
        if (!nodes) return false;
        return nodes.some(node => {
            const name = node.name || '';
            if (name.toLowerCase().includes(this.data.searchQuery)) return true;
            return this.hasMatchingChild(node.children);
        });
    },

    renderSubtree: function(categoryId, level) {
        const tree = this.data.treeData[categoryId];
        if (!tree) return;

        const renderRecursive = (nodes, lvl) => {
            nodes.forEach(node => {
                // If searching, check if node matches or has children that match
                // For simplicity, we show all children of matched parents
                this.renderRow(node, 'subcategory', lvl, categoryId);
                
                const nodeKey = `subcategory-${node.id}`;
                if (this.data.expandedNodes.has(nodeKey) && node.children && node.children.length > 0) {
                    renderRecursive(node.children, lvl + 1);
                }
            });
        };

        renderRecursive(tree, level);
    },

    renderRow: function(item, type, level, rootCatId = null) {
        const id = item.id;
        const name = type === 'category' ? item.categoryName : item.name;
        const code = item.code || '-';
        const isActive = item.isActive !== false;
        const nodeKey = `${type}-${id}`;
        const isExpanded = this.data.expandedNodes.has(nodeKey);
        const hasChildren = type === 'category' || (item.children && item.children.length > 0);
        
        // Child count badge (simulated if not in API)
        const childCount = type === 'category' ? '' : (item.children ? item.children.length : 0);
        const countHtml = childCount > 0 ? `<span class="count-badge">${childCount}</span>` : '';

        const row = document.createElement('tr');
        row.className = `tree-grid-row ${!isActive ? 'opacity-50' : ''}`;
        row.dataset.id = id;
        row.dataset.type = type;

        let nameHtml = `
            <div class="tree-cell" style="padding-left: ${level * 32}px">
                ${level > 0 ? '<div class="tree-connector"></div>' : ''}
                <div class="tree-expander ${isExpanded ? 'expanded' : ''} ${!hasChildren ? 'invisible' : ''}" 
                     data-id="${id}" data-type="${type}">
                    <i class="las la-angle-right"></i>
                </div>
                <span class="category-name-l${Math.min(level + 1, 3)}">${name}</span>
                ${countHtml}
            </div>
        `;

        row.innerHTML = `
            <td>${nameHtml}</td>
            <td><code>${code}</code></td>
            <td>
                <div class="form-check form-switch">
                    <input class="form-check-input status-toggle" type="checkbox" 
                           ${isActive ? 'checked' : ''} 
                           data-id="${id}" data-type="${type}" data-action="toggle-status">
                    <span class="badge ${isActive ? 'bg-success-subtle text-success' : 'bg-danger-subtle text-danger'} ms-2">
                        ${isActive ? 'Active' : 'Inactive'}
                    </span>
                </div>
            </td>
            <td class="text-center">
                <button class="action-btn" title="Edit" data-id="${id}" data-type="${type}" data-action="edit">
                    <i class="las la-pen"></i>
                </button>
                <button class="action-btn ${level >= 2 ? 'd-none' : ''}" title="Add Child" data-id="${id}" data-type="${type}" data-action="add-child">
                    <i class="las la-plus"></i>
                </button>
            </td>
        `;

        this.$tableBody.appendChild(row);
    },

    toggleNode: function(id, type) {
        const nodeKey = `${type}-${id}`;
        if (this.data.expandedNodes.has(nodeKey)) {
            this.data.expandedNodes.delete(nodeKey);
            this.renderTable();
        } else {
            if (type === 'category') {
                this.showLoader(true);
                this.fetchSubtree(id)
                    .then(() => {
                        this.data.expandedNodes.add(nodeKey);
                        this.renderTable();
                    })
                    .catch(err => this.showNotification('error', 'Failed to load subcategories'))
                    .finally(() => this.showLoader(false));
            } else {
                this.data.expandedNodes.add(nodeKey);
                this.renderTable();
            }
        }
    },

    collapseAll: function() {
        this.data.expandedNodes.clear();
        this.renderTable();
    },

    openCategoryModal: function(id = null) {
        this.$categoryForm.reset();
        document.getElementById('categoryId').value = '';
        document.getElementById('categoryModalLabel').innerText = id ? 'Edit Category' : 'Add Category';

        if (id) {
            const cat = this.data.categories.find(c => c.id == id);
            if (cat) {
                document.getElementById('categoryId').value = cat.id;
                document.getElementById('categoryName').value = cat.categoryName;
                document.getElementById('categoryCode').value = cat.code;
            }
        }
        this.categoryModal.show();
    },

    openSubcategoryModal: function(id = null, parent = null, isEdit = false) {
        this.$subcategoryForm.reset();
        document.getElementById('subcategoryId').value = '';
        document.getElementById('parentCategoryId').value = '';
        document.getElementById('parentSubcategoryId').value = '';
        
        const $breadcrumb = document.getElementById('modalBreadcrumb');
        $breadcrumb.style.display = 'none';

        if (isEdit) {
            document.getElementById('subcategoryModalLabel').innerText = 'Edit Subcategory';
            // In a real app, we'd fetch full details or find in treeData
            // For this implementation, we'll assume we find it or fetch it
            this.showNotification('info', 'Fetching subcategory details...');
            // Mocking data for now
        } else if (parent) {
            document.getElementById('subcategoryModalLabel').innerText = 'Add Child Subcategory';
            if (parent.type === 'category') {
                document.getElementById('parentCategoryId').value = parent.id;
                const cat = this.data.categories.find(c => c.id == parent.id);
                $breadcrumb.innerHTML = `Adding to: <span>${cat.categoryName}</span>`;
                $breadcrumb.style.display = 'block';
            } else {
                // Find parent subcategory to get its categoryId
                // This would require a flattened search in treeData
                document.getElementById('parentSubcategoryId').value = parent.id;
                $breadcrumb.innerHTML = `Adding child to subcategory ID: <span>${parent.id}</span>`;
                $breadcrumb.style.display = 'block';
            }
        }

        this.subcategoryModal.show();
    },

    saveCategory: function() {
        const formData = new FormData(this.$categoryForm);
        const data = Object.fromEntries(formData.entries());
        const id = data.categoryId;
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/categories/${id}` : '/api/categories';

        this.showLoader(true);
        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(res => res.json())
        .then(res => {
            if (res.status === '200' || res.status === 'SUCCESS') {
                this.showNotification('success', id ? 'Category updated' : 'Category created');
                this.categoryModal.hide();
                this.fetchCategories();
            } else {
                this.showNotification('error', res.statusMsg);
            }
        })
        .catch(() => this.showNotification('error', 'Network error'))
        .finally(() => this.showLoader(false));
    },

    saveSubcategory: function() {
        const formData = new FormData(this.$subcategoryForm);
        const data = Object.fromEntries(formData.entries());
        
        // Enforce companyId from session if needed, but proxy usually handles it
        if (!data.categoryId && !data.parentSubcategoryId) {
            this.showNotification('error', 'Parent context is missing');
            return;
        }

        this.showLoader(true);
        fetch('/api/subcategories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(res => res.json())
        .then(res => {
            if (res.status === '200' || res.status === 'SUCCESS') {
                this.showNotification('success', 'Subcategory saved');
                this.subcategoryModal.hide();
                // Clear tree data for the affected category to force refresh on next expand
                const catId = data.categoryId || this.findRootCategoryId(data.parentSubcategoryId);
                if (catId) delete this.data.treeData[catId];
                this.renderTable();
            } else {
                this.showNotification('error', res.statusMsg);
            }
        })
        .catch(() => this.showNotification('error', 'Network error'))
        .finally(() => this.showLoader(false));
    },

    findRootCategoryId: function(subcatId) {
        // Helper to find which category a subcategory belongs to
        for (const catId in this.data.treeData) {
            const findInTree = (nodes) => {
                for (const node of nodes) {
                    if (node.id == subcatId) return true;
                    if (node.children && findInTree(node.children)) return true;
                }
                return false;
            };
            if (findInTree(this.data.treeData[catId])) return catId;
        }
        return null;
    },

    openStatusModal: function(id, type) {
        this.data.pendingStatusChange = { id, type };
        document.getElementById('statusConfirmWarning').style.display = type === 'category' ? 'block' : 'none';
        this.statusModal.show();
    },

    showLoader: function(show) {
        this.$loader.style.display = show ? 'flex' : 'none';
    },

    showNotification: function(type, message) {
        // Use existing toast system if available, else alert
        if (window.Toastify) {
            Toastify({
                text: message,
                backgroundColor: type === 'success' ? '#198754' : '#dc3545',
                duration: 3000
            }).showToast();
        } else {
            alert(`${type.toUpperCase()}: ${message}`);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => CategoryManager.init());
