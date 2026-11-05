/**
 * LUXE-TRACE - Settings & User Management Modal Controller
 * Handles user profile, password change, and admin user administration.
 */

window.addEventListener('DOMContentLoaded', () => {
  setupSettingsModal();
});

function setupSettingsModal() {
  const overlay = document.getElementById('overlay-settings');
  const btnOpen = document.getElementById('btn-open-settings');
  const btnClose = document.getElementById('btn-close-settings');

  if (!overlay) return;

  // Open modal
  if (btnOpen) {
    btnOpen.addEventListener('click', (e) => {
      e.preventDefault();
      overlay.classList.add('active');
      // If admin tab exists, load users table proactively
      const usersTab = document.getElementById('tab-btn-settings-users');
      if (usersTab) {
        loadAdminUsersTable();
      }
    });
  }

  // Close modal
  if (btnClose) {
    btnClose.addEventListener('click', () => {
      overlay.classList.remove('active');
    });
  }

  // Close on backdrop click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.classList.remove('active');
    }
  });

  // Tab switching
  const tabAccount = document.getElementById('tab-btn-settings-account');
  const tabUsers = document.getElementById('tab-btn-settings-users');
  const contentAccount = document.getElementById('tab-content-settings-account');
  const contentUsers = document.getElementById('tab-content-settings-users');

  if (tabAccount && tabUsers) {
    tabAccount.addEventListener('click', () => {
      tabAccount.classList.add('active');
      tabUsers.classList.remove('active');
      if (contentAccount) contentAccount.classList.add('active');
      if (contentUsers) contentUsers.classList.remove('active');
    });

    tabUsers.addEventListener('click', () => {
      tabUsers.classList.add('active');
      tabAccount.classList.remove('active');
      if (contentUsers) contentUsers.classList.add('active');
      if (contentAccount) contentAccount.classList.remove('active');
      loadAdminUsersTable();
    });
  }

  // Password change submission
  const formPass = document.getElementById('form-change-password');
  if (formPass) {
    formPass.addEventListener('submit', handlePasswordChange);
  }

  // Create user submission (Admin only)
  const formUser = document.getElementById('form-create-user');
  if (formUser) {
    formUser.addEventListener('submit', handleCreateUser);
  }
}

function handlePasswordChange(e) {
  e.preventDefault();
  const currentPass = document.getElementById('input-current-pass')?.value || '';
  const newPass = document.getElementById('input-new-pass')?.value || '';
  const confirmPass = document.getElementById('input-confirm-pass')?.value || '';
  const feedback = document.getElementById('account-pass-feedback');
  const submitBtn = document.getElementById('btn-change-pass');

  if (!feedback) return;

  if (newPass !== confirmPass) {
    showFeedback(feedback, 'New passwords do not match.', 'error');
    return;
  }

  if (newPass.length < 6) {
    showFeedback(feedback, 'New password must be at least 6 characters.', 'error');
    return;
  }

  if (submitBtn) submitBtn.disabled = true;

  fetch('/api/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_password: currentPass,
      new_password: newPass
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.status === 'success') {
        showFeedback(feedback, 'Password updated successfully!', 'success');
        document.getElementById('form-change-password').reset();
      } else {
        showFeedback(feedback, data.message || 'Failed to update password.', 'error');
      }
    })
    .catch(err => {
      showFeedback(feedback, 'Network error: ' + err, 'error');
    })
    .finally(() => {
      if (submitBtn) submitBtn.disabled = false;
    });
}

function handleCreateUser(e) {
  e.preventDefault();
  const username = document.getElementById('input-admin-new-user')?.value || '';
  const password = document.getElementById('input-admin-new-pass')?.value || '';
  const role = document.getElementById('select-admin-new-role')?.value || 'operator';
  const feedback = document.getElementById('admin-create-user-feedback');
  const submitBtn = document.getElementById('btn-admin-add-user');

  if (!feedback) return;

  if (submitBtn) submitBtn.disabled = true;

  fetch('/api/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: username,
      password: password,
      role: role
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.status === 'success') {
        showFeedback(feedback, `User '${username}' created successfully as ${role.toUpperCase()}.`, 'success');
        document.getElementById('form-create-user').reset();
        loadAdminUsersTable();
      } else {
        showFeedback(feedback, data.message || 'Failed to create user.', 'error');
      }
    })
    .catch(err => {
      showFeedback(feedback, 'Network error: ' + err, 'error');
    })
    .finally(() => {
      if (submitBtn) submitBtn.disabled = false;
    });
}

function loadAdminUsersTable() {
  const tbody = document.getElementById('table-admin-users-body');
  if (!tbody) return;

  fetch('/api/admin/users')
    .then(res => res.json())
    .then(data => {
      if (data.status === 'success' && data.users) {
        renderUsersTable(data.users, data.current_user);
      } else {
        tbody.innerHTML = `<tr><td colspan="4" style="color:#f43f5e; text-align:center;">${data.message || 'Failed to load users'}</td></tr>`;
      }
    })
    .catch(err => {
      tbody.innerHTML = `<tr><td colspan="4" style="color:#f43f5e; text-align:center;">Network error loading users</td></tr>`;
    });
}

function renderUsersTable(users, currentUser) {
  const tbody = document.getElementById('table-admin-users-body');
  if (!tbody) return;

  if (!users || users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim);">No accounts found.</td></tr>`;
    return;
  }

  tbody.innerHTML = '';
  users.forEach(u => {
    const tr = document.createElement('tr');
    const isSelf = u.username.toLowerCase() === (currentUser || '').toLowerCase();
    const roleBadgeClass = u.role === 'admin' ? 'role-admin' : 'role-operator';

    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(u.username)}</strong>
        ${isSelf ? '<span class="you-tag">(YOU)</span>' : ''}
      </td>
      <td>
        <span class="role-badge ${roleBadgeClass}">${escapeHtml((u.role || 'operator').toUpperCase())}</span>
      </td>
      <td style="color:var(--text-dim); font-size:0.75rem;">
        ${escapeHtml(u.created_at || '--')}
      </td>
      <td style="text-align: right;">
        ${!isSelf ? `
          <button class="btn-delete-user" data-user="${escapeHtml(u.username)}" title="Delete user">
            Delete
          </button>
        ` : '<span style="color:var(--text-dim); font-size:0.7rem;">Active Session</span>'}
      </td>
    `;

    tbody.appendChild(tr);
  });

  // Attach delete handlers
  tbody.querySelectorAll('.btn-delete-user').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetUser = btn.dataset.user;
      if (confirm(`Are you sure you want to permanently delete user account '${targetUser}'?`)) {
        deleteUserAccount(targetUser);
      }
    });
  });
}

function deleteUserAccount(username) {
  fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: 'DELETE'
  })
    .then(res => res.json())
    .then(data => {
      if (data.status === 'success') {
        loadAdminUsersTable();
      } else {
        alert('Error deleting user: ' + (data.message || 'Unknown error'));
      }
    })
    .catch(err => {
      alert('Network error deleting user: ' + err);
    });
}

function showFeedback(el, msg, type) {
  el.style.display = 'block';
  el.className = `settings-feedback ${type}`;
  el.textContent = msg;
  setTimeout(() => {
    el.style.display = 'none';
  }, 5000);
}

