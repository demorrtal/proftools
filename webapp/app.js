// Telegram Web App Client JS
const tg = window.Telegram?.WebApp;

// Состояние приложения
let state = {
  user: null,
  isRegistered: false,
  isAdmin: false,
  isCleaningRole: false,
  roles: [],
  takenRoles: [],
  currentTab: 'tab-tasks',
  taskFilter: 'active',
  tasks: [],
  selectedRolesForNewTask: [],
  extendTaskId: null
};

// Инициализация WebApp
document.addEventListener('DOMContentLoaded', async () => {
  if (tg) {
    tg.ready();
    tg.expand();
    // Применяем цвета Telegram
    document.documentElement.style.setProperty('--tg-theme-bg-color', tg.backgroundColor || '#0f172a');
    document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', tg.secondaryBackgroundColor || '#1e293b');
  }

  // Получаем пользователя Telegram
  const tgUser = tg?.initDataUnsafe?.user || {
    id: 12345678,
    first_name: "Тестовый",
    last_name: "Пользователь",
    username: "testuser"
  };

  await loadUserProfile(tgUser);
  setupEventHandlers();
  await loadTasks();
});

// Вибрация Telegram Haptic
function haptic(type = 'light') {
  try {
    if (tg?.HapticFeedback) {
      if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
      else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
      else tg.HapticFeedback.impactOccurred(type);
    }
  } catch (e) {}
}

// 1. Профиль и регистрация
async function loadUserProfile(tgUser) {
  try {
    const res = await fetch(`/api/me?user_id=${tgUser.id}`);
    const data = await res.json();

    state.roles = data.roles || [];
    state.takenRoles = data.taken_roles || [];

    if (!data.registered) {
      // Пользователь не зарегистрирован -> показываем модалку регистрации
      state.isRegistered = false;
      showRegistrationModal(tgUser);
    } else {
      state.isRegistered = true;
      state.user = data.user;
      state.isAdmin = data.is_admin;
      state.isCleaningRole = data.is_cleaning;

      renderHeader();
      updateAdminVisibility();
    }
  } catch (err) {
    console.error('Ошибка загрузки профиля:', err);
  }
}

function renderHeader() {
  if (!state.user) return;
  const avatar = document.getElementById('userAvatar');
  const nameEl = document.getElementById('userName');
  const badgeEl = document.getElementById('userRoleBadge');

  const initials = `${state.user.first_name?.[0] || ''}${state.user.last_name?.[0] || ''}`.toUpperCase();
  avatar.textContent = initials || '👤';
  nameEl.textContent = `${state.user.first_name} ${state.user.last_name}`;
  
  const adminIcon = state.isAdmin ? '👑 ' : '💼 ';
  badgeEl.textContent = `${adminIcon}${state.user.role}`;
}

function updateAdminVisibility() {
  const createNavBtn = document.getElementById('navCreateBtn');
  if (createNavBtn) {
    if (state.isAdmin) {
      createNavBtn.classList.remove('hidden');
    } else {
      createNavBtn.classList.add('hidden');
    }
  }

  const addCleaningBtn = document.getElementById('openAddCleaningBtn');
  if (addCleaningBtn) {
    addCleaningBtn.style.display = (state.isAdmin || state.isCleaningRole) ? 'inline-flex' : 'none';
  }
}

function showRegistrationModal(tgUser) {
  const modal = document.getElementById('registerModal');
  const select = document.getElementById('regRoleSelect');
  document.getElementById('regFirstName').value = tgUser.first_name || '';
  document.getElementById('regLastName').value = tgUser.last_name || '';

  // Заполняем свободные роли
  select.innerHTML = '';
  state.roles.forEach(role => {
    if (!state.takenRoles.includes(role)) {
      const opt = document.createElement('option');
      opt.value = role;
      opt.textContent = role;
      select.appendChild(opt);
    }
  });

  modal.classList.add('active');

  document.getElementById('submitRegBtn').onclick = async () => {
    const fn = document.getElementById('regFirstName').value.trim();
    const ln = document.getElementById('regLastName').value.trim();
    const grp = document.getElementById('regGroup').value.trim();
    const role = select.value;

    if (!fn || !ln || !role) {
      alert('Пожалуйста, заполните имя, фамилию и выберите должность!');
      return;
    }

    try {
      const resp = await fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: tgUser.id,
          first_name: fn,
          last_name: ln,
          group_number: grp,
          username: tgUser.username,
          role: role
        })
      });

      if (!resp.ok) {
        const err = await resp.json();
        alert(err.detail || 'Ошибка регистрации');
        return;
      }

      haptic('success');
      modal.classList.remove('active');
      await loadUserProfile(tgUser);
      await loadTasks();
    } catch (e) {
      alert('Ошибка соединения при регистрации: ' + e);
    }
  };
}

// 2. Список задач
async function loadTasks() {
  const container = document.getElementById('tasksList');
  if (!state.user) return;

  container.innerHTML = '<div class="loading-spinner">Загрузка задач...</div>';

  try {
    const res = await fetch(`/api/tasks?user_id=${state.user.user_id}&filter_type=${state.taskFilter}`);
    const data = await res.json();
    state.tasks = data.tasks || [];
    renderTasksList();
  } catch (e) {
    container.innerHTML = '<div class="empty-state">Не удалось загрузить задачи.</div>';
  }
}

function renderTasksList() {
  const container = document.getElementById('tasksList');
  if (!state.tasks || state.tasks.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 32px; margin-bottom: 8px;">🎉</div>
        <b>Задач в этом разделе нет!</b>
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  state.tasks.forEach(t => {
    const card = document.createElement('div');
    card.className = 'task-card';

    let badgeClass = 'active';
    let badgeText = 'В работе';
    if (t.badge === 'completed') {
      badgeClass = 'completed';
      badgeText = 'Выполнена';
    } else if (t.badge === 'overdue') {
      badgeClass = 'overdue';
      badgeText = 'Просрочена';
    } else if (t.badge === 'today') {
      badgeClass = 'today';
      badgeText = 'Сегодня';
    } else {
      badgeClass = 'active';
      badgeText = t.badge;
    }

    let actionsHtml = '';
    if (state.isAdmin && t.status !== 'completed') {
      actionsHtml = `
        <div class="task-actions">
          <button class="btn btn-sm btn-success complete-task-btn" data-id="${t.id}">✅ Выполнено</button>
          <button class="btn btn-sm btn-secondary extend-task-btn" data-id="${t.id}" data-title="${encodeURIComponent(t.title)}">⏳ Продлить</button>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="task-card-header">
        <span class="task-id">Задача #${t.id}</span>
        <span class="task-badge ${badgeClass}">${badgeText}</span>
      </div>
      <div class="task-title">${escapeHtml(t.title)}</div>
      <div class="task-info-row">
        <span class="task-info-label">👥 Кому:</span>
        <span class="task-info-val">${escapeHtml(t.target_roles_display)}</span>
      </div>
      <div class="task-info-row">
        <span class="task-info-label">⏰ Дедлайн:</span>
        <span class="task-info-val">${escapeHtml(t.formatted_deadline)}</span>
      </div>
      <div class="task-info-row">
        <span class="task-info-label">👤 Поставил:</span>
        <span class="task-info-val">${escapeHtml(t.creator_name)}</span>
      </div>
      ${actionsHtml}
    `;

    container.appendChild(card);
  });

  // Обработчики кнопок карточек
  container.querySelectorAll('.complete-task-btn').forEach(btn => {
    btn.onclick = async () => {
      const taskId = btn.dataset.id;
      if (!confirm(`Отметить задачу #${taskId} как выполненную?`)) return;
      haptic('medium');
      await completeTaskApi(taskId);
    };
  });

  container.querySelectorAll('.extend-task-btn').forEach(btn => {
    btn.onclick = () => {
      haptic('light');
      openExtendModal(btn.dataset.id, decodeURIComponent(btn.dataset.title));
    };
  });
}

async function completeTaskApi(taskId) {
  try {
    const res = await fetch(`/api/tasks/${taskId}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.user.user_id })
    });
    if (res.ok) {
      haptic('success');
      await loadTasks();
    }
  } catch (e) {
    alert('Ошибка при закрытии задачи: ' + e);
  }
}

// 3. Создание задачи
function setupCreateTaskForm() {
  const grid = document.getElementById('rolesGrid');
  grid.innerHTML = '';

  state.selectedRolesForNewTask = [];
  state.roles.forEach(role => {
    const pill = document.createElement('div');
    pill.className = 'role-pill';
    pill.textContent = role;
    pill.onclick = () => {
      haptic('light');
      if (state.selectedRolesForNewTask.includes('ALL')) {
        state.selectedRolesForNewTask = [];
        grid.querySelectorAll('.role-pill').forEach(p => p.classList.remove('selected'));
      }

      if (state.selectedRolesForNewTask.includes(role)) {
        state.selectedRolesForNewTask = state.selectedRolesForNewTask.filter(r => r !== role);
        pill.classList.remove('selected');
      } else {
        state.selectedRolesForNewTask.push(role);
        pill.classList.add('selected');
      }
    };
    grid.appendChild(pill);
  });

  // Кнопка ВСЕ
  const allBtn = document.getElementById('toggleAllRolesBtn');
  allBtn.onclick = () => {
    haptic('medium');
    const isAll = state.selectedRolesForNewTask.includes('ALL');
    const pills = grid.querySelectorAll('.role-pill');
    if (isAll) {
      state.selectedRolesForNewTask = [];
      pills.forEach(p => p.classList.remove('selected'));
      allBtn.textContent = 'Выбрать ВСЕ';
    } else {
      state.selectedRolesForNewTask = ['ALL'];
      pills.forEach(p => p.classList.add('selected'));
      allBtn.textContent = 'Снять выбор';
    }
  };

  // Отправка формы
  document.getElementById('submitTaskBtn').onclick = async () => {
    const title = document.getElementById('taskTitleInput').value.trim();
    const deadlineVal = document.getElementById('taskDeadlineInput').value;

    if (!title) {
      alert('Введите суть задачи!');
      return;
    }
    if (state.selectedRolesForNewTask.length === 0) {
      alert('Выберите исполнителей (хотя бы одну должность или вариант ВСЕ)!');
      return;
    }
    if (!deadlineVal) {
      alert('Укажите дату и время дедлайна!');
      return;
    }

    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          creator_id: state.user.user_id,
          title: title,
          target_roles: state.selectedRolesForNewTask.includes('ALL') ? 'ALL' : state.selectedRolesForNewTask,
          deadline: deadlineVal
        })
      });

      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Ошибка создания задачи');
        return;
      }

      haptic('success');
      alert('🎉 Задача успешно создана и отправлена в группу!');
      document.getElementById('taskTitleInput').value = '';
      document.getElementById('taskDeadlineInput').value = '';
      
      // Переключаем на таб задач
      switchTab('tab-tasks');
      await loadTasks();
    } catch (e) {
      alert('Ошибка при создании задачи: ' + e);
    }
  };
}

// 4. График уборки
async function loadCleaningSchedule() {
  const container = document.getElementById('cleaningList');
  container.innerHTML = '<div class="loading-spinner">Загрузка...</div>';
  try {
    const res = await fetch('/api/cleaning');
    const data = await res.json();
    const dates = data.dates || [];

    if (dates.length === 0) {
      container.innerHTML = '<div class="empty-state">Даты уборки пока не запланированы.</div>';
      return;
    }

    container.innerHTML = '';
    dates.forEach(d => {
      const item = document.createElement('div');
      item.className = 'cleaning-item';
      
      let delBtn = '';
      if (state.isAdmin || state.isCleaningRole) {
        delBtn = `<button class="btn btn-sm btn-danger del-clean-btn" data-id="${d.id}">Удалить</button>`;
      }

      item.innerHTML = `
        <div>
          <div class="cleaning-date">📅 ${escapeHtml(d.cleaning_date)}</div>
          ${d.comment ? `<div class="cleaning-comment">${escapeHtml(d.comment)}</div>` : ''}
        </div>
        ${delBtn}
      `;
      container.appendChild(item);
    });

    container.querySelectorAll('.del-clean-btn').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Удалить эту дату уборки?')) return;
        haptic('medium');
        await fetch(`/api/cleaning/${btn.dataset.id}?user_id=${state.user.user_id}`, { method: 'DELETE' });
        await loadCleaningSchedule();
      };
    });
  } catch (e) {
    container.innerHTML = '<div class="empty-state">Ошибка загрузки графика.</div>';
  }
}

// 5. Команда
async function loadTeam() {
  const container = document.getElementById('teamList');
  container.innerHTML = '<div class="loading-spinner">Загрузка...</div>';

  try {
    const res = await fetch('/api/team');
    const data = await res.json();
    const roster = data.team || [];

    container.innerHTML = '';
    roster.forEach(item => {
      const el = document.createElement('div');
      el.className = 'team-item';

      const u = item.user;
      let userDetails = '<span style="color: var(--hint-color); font-style: italic;">Вакансия свободна</span>';
      let actionBtn = '';

      if (u) {
        const grp = u.group_number ? ` [Гр. ${u.group_number}]` : '';
        const tgLink = u.username ? ` (@${u.username})` : '';
        userDetails = `<b>${escapeHtml(u.first_name)} ${escapeHtml(u.last_name)}</b>${grp}${tgLink}`;

        if (state.isAdmin && u.user_id !== state.user.user_id) {
          actionBtn = `<button class="btn btn-sm btn-danger remove-user-btn" data-uid="${u.user_id}" data-role="${u.role}">Снять</button>`;
        }
      }

      el.innerHTML = `
        <div>
          <div class="team-role">${item.role}</div>
          <div class="team-person">${userDetails}</div>
        </div>
        ${actionBtn}
      `;
      container.appendChild(el);
    });

    container.querySelectorAll('.remove-user-btn').forEach(b => {
      b.onclick = async () => {
        if (!confirm(`Снять сотрудника с должности ${b.dataset.role}?`)) return;
        haptic('medium');
        await fetch('/api/team/remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ admin_id: state.user.user_id, target_user_id: parseInt(b.dataset.uid) })
        });
        await loadTeam();
      };
    });

  } catch (e) {
    container.innerHTML = '<div class="empty-state">Ошибка загрузки команды.</div>';
  }
}

// 6. Темы форума и настройки
async function loadSettings() {
  try {
    const [settingsRes, topicsRes] = await Promise.all([
      fetch('/api/settings'),
      fetch('/api/topics')
    ]);
    const settings = await settingsRes.json();
    const topicsData = await topicsRes.json();

    // Ссылка на Google Таблицу
    const link = document.getElementById('workplanLink');
    if (settings.workplan_url) link.href = settings.workplan_url;

    // Выбор темы
    const container = document.getElementById('topicsSelector');
    container.innerHTML = '';

    const activeTopicId = String(topicsData.active_topic_id || '');

    // Опция "Основной чат (без темы)"
    const generalCard = document.createElement('div');
    generalCard.className = `topic-radio-card ${!activeTopicId ? 'active' : ''}`;
    generalCard.innerHTML = `
      <span style="font-size: 18px;">💬</span>
      <div>
        <div style="font-weight: 600; font-size: 14px;">Основной чат (без топика)</div>
        <div style="font-size: 12px; color: var(--hint-color);">Публиковать в общий раздел группы</div>
      </div>
    `;
    generalCard.onclick = () => selectTopicApi('none');
    container.appendChild(generalCard);

    // Список тем форума
    (topicsData.topics || []).forEach(top => {
      const card = document.createElement('div');
      const isActive = (String(top.thread_id) === activeTopicId);
      card.className = `topic-radio-card ${isActive ? 'active' : ''}`;
      card.innerHTML = `
        <span style="font-size: 18px;">📌</span>
        <div>
          <div style="font-weight: 600; font-size: 14px;">${escapeHtml(top.title)}</div>
          <div style="font-size: 12px; color: var(--hint-color);">ID темы: ${top.thread_id}</div>
        </div>
      `;
      card.onclick = () => selectTopicApi(top.thread_id);
      container.appendChild(card);
    });

  } catch (e) {
    console.error('Ошибка загрузки настроек:', e);
  }
}

async function selectTopicApi(threadId) {
  if (!state.isAdmin) {
    alert('Только Председатель может переключать тему форума!');
    return;
  }
  haptic('medium');
  try {
    await fetch('/api/topics/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.user.user_id, thread_id: threadId })
    });
    haptic('success');
    await loadSettings();
  } catch (e) {
    alert('Ошибка смены темы: ' + e);
  }
}

// 7. Модалка продления дедлайна
function openExtendModal(taskId, title) {
  state.extendTaskId = taskId;
  document.getElementById('extendTaskTitle').textContent = `Задача #${taskId}: ${title}`;
  document.getElementById('extendModal').classList.add('active');
}

// 8. Переключение табов и события
function setupEventHandlers() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.onclick = () => {
      haptic('light');
      const targetTab = btn.dataset.tab;
      switchTab(targetTab);
    };
  });

  document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.onclick = () => {
      haptic('light');
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.taskFilter = pill.dataset.filter;
      loadTasks();
    };
  });

  // Кнопка обновления
  document.getElementById('refreshBtn').onclick = () => {
    haptic('medium');
    if (state.currentTab === 'tab-tasks') loadTasks();
    else if (state.currentTab === 'tab-cleaning') loadCleaningSchedule();
    else if (state.currentTab === 'tab-team') loadTeam();
    else if (state.currentTab === 'tab-settings') loadSettings();
  };

  // Модалка добавления уборки
  document.getElementById('openAddCleaningBtn').onclick = () => {
    haptic('light');
    document.getElementById('cleaningModal').classList.add('active');
  };
  document.getElementById('cancelCleaningBtn').onclick = () => {
    document.getElementById('cleaningModal').classList.remove('active');
  };
  document.getElementById('confirmCleaningBtn').onclick = async () => {
    const dVal = document.getElementById('newCleaningDateInput').value.trim();
    const cVal = document.getElementById('newCleaningCommentInput').value.trim();
    if (!dVal) return alert('Введите дату уборки!');
    haptic('medium');
    await fetch('/api/cleaning', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.user.user_id, cleaning_date: dVal, comment: cVal })
    });
    haptic('success');
    document.getElementById('cleaningModal').classList.remove('active');
    document.getElementById('newCleaningDateInput').value = '';
    document.getElementById('newCleaningCommentInput').value = '';
    await loadCleaningSchedule();
  };

  // Модалка продления
  document.getElementById('cancelExtendBtn').onclick = () => {
    document.getElementById('extendModal').classList.remove('active');
  };
  document.getElementById('confirmExtendBtn').onclick = async () => {
    const newDl = document.getElementById('extendDeadlineInput').value;
    if (!newDl) return alert('Укажите новую дату!');
    haptic('medium');
    const res = await fetch(`/api/tasks/${state.extendTaskId}/extend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.user.user_id, new_deadline: newDl })
    });
    if (res.ok) {
      haptic('success');
      document.getElementById('extendModal').classList.remove('active');
      await loadTasks();
    } else {
      const err = await res.json();
      alert(err.detail || 'Ошибка продления');
    }
  };
}

function switchTab(tabId) {
  state.currentTab = tabId;
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const activePane = document.getElementById(tabId);
  const activeNav = document.querySelector(`.nav-item[data-tab="${tabId}"]`);

  if (activePane) activePane.classList.add('active');
  if (activeNav) activeNav.classList.add('active');

  if (tabId === 'tab-tasks') loadTasks();
  else if (tabId === 'tab-create') setupCreateTaskForm();
  else if (tabId === 'tab-cleaning') loadCleaningSchedule();
  else if (tabId === 'tab-team') loadTeam();
  else if (tabId === 'tab-settings') loadSettings();
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
