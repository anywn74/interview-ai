// 底层请求封装：返回 {data, headers}，headers 供需要读取响应头的接口使用
async function apiMeta(path, method, body) {
  const options = {
    method: method,
    headers: { "Content-Type": "application/json" }
  };
  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (response.status !== 200) {
    // 422 校验错误的 detail 是数组，取第一条错误信息显示，其余错误取 detail 字符串
    let msg = data.detail || ("HTTP " + response.status);
    if (Array.isArray(data.detail) && data.detail.length > 0) {
      msg = data.detail[0].msg || JSON.stringify(data.detail[0]);
    }
    throw new Error(msg);
  }
  return { data: data, headers: response.headers };
}

// 统一网络请求封装：大多数接口只需要 JSON 数据，调用上一层的 apiMeta 再取 data
async function api(path, method, body) {
  const result = await apiMeta(path, method, body);
  return result.data;
}

// 流式请求：POST 到 SSE 接口后边接收边调用 onChunk 逐块处理，返回拼接好的完整文本
// 服务端非 200 时抛出 detail 错误信息；流中断时抛出"流式读取失败"
async function ssePost(path, body, onChunk) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    let msg = "请求失败";
    try {
      const data = await response.json();
      msg = data.detail || ("HTTP " + response.status);
    } catch (e) {}
    throw new Error(msg);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";
  let errorText = "";
  while (true) {
    const part = await reader.read();
    if (part.done) break;
    buffer += decoder.decode(part.value, { stream: true });
    // SSE 按空行分隔事件、按行组织字段，这里逐行解析 data 字段
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (line === "event: error") {
        errorText = "流式读取失败";
        continue;
      }
      if (errorText) continue;
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (data === "[DONE]") continue;
      try {
        const obj = JSON.parse(data);
        if (obj.content) {
          fullText += obj.content;
          onChunk(obj.content);
        }
      } catch (e) {}
    }
  }
  if (errorText) {
    throw new Error(errorText);
  }
  return fullText;
}

// 登录成功后保存用户信息，多个页面共用同一份登录态
function saveUser(id, name) {
  localStorage.setItem("interview_ai_user", JSON.stringify({ id: id, name: name }));
  showUser();
}

// 读取登录态并更新导航栏右上角：已登录显示用户名和统计/记录/个人中心链接，未登录显示登录/注册按钮
function showUser() {
  const info = document.getElementById("user-info");
  const loginBtn = document.getElementById("nav-login");
  const registerBtn = document.getElementById("nav-register");
  const logoutBtn = document.getElementById("nav-logout");
  const statsLink = document.getElementById("nav-stats");
  const recordsLink = document.getElementById("nav-records");
  const profileLink = document.getElementById("nav-profile");
  const raw = localStorage.getItem("interview_ai_user");
  if (raw) {
    const user = JSON.parse(raw);
    if (info) info.textContent = "当前用户：" + user.name + "（id " + user.id + "）";
    if (loginBtn) loginBtn.classList.add("d-none");
    if (registerBtn) registerBtn.classList.add("d-none");
    if (logoutBtn) logoutBtn.classList.remove("d-none");
    if (statsLink) statsLink.classList.remove("d-none");
    if (recordsLink) recordsLink.classList.remove("d-none");
    if (profileLink) profileLink.classList.remove("d-none");
  } else {
    if (info) info.textContent = "未登录";
    if (loginBtn) loginBtn.classList.remove("d-none");
    if (registerBtn) registerBtn.classList.remove("d-none");
    if (logoutBtn) logoutBtn.classList.add("d-none");
    if (statsLink) statsLink.classList.add("d-none");
    if (recordsLink) recordsLink.classList.add("d-none");
    if (profileLink) profileLink.classList.add("d-none");
  }
}

// 读取当前登录用户信息 {id,name}；未登录返回 null
function currentUser() {
  const raw = localStorage.getItem("interview_ai_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

// 判断是否已登录（localStorage 中有用户信息就算登录）
function isLoggedIn() {
  return localStorage.getItem("interview_ai_user") !== null;
}

// 页面级登录守卫：统计/答题记录/个人中心等个人数据页未登录直接跳转登录页
function requireAuth() {
  if (!isLoggedIn()) {
    location.href = "/login";
  }
}

// 登出：清除本地登录态，导航栏恢复为"未登录"；在个人数据页登出后自动回主页
function logout() {
  localStorage.removeItem("interview_ai_user");
  showUser();
  if (["/stats", "/records", "/profile"].indexOf(location.pathname) !== -1) {
    location.href = "/";
  }
}

// 按难度返回 Bootstrap 徽章颜色
function difficultyColor(difficulty) {
  if (difficulty === "简单") return "bg-success";
  if (difficulty === "中等") return "bg-warning text-dark";
  if (difficulty === "困难") return "bg-danger";
  return "bg-secondary";
}

// 筛选下拉框初始化：从全部题目中收集不重复的分类和难度作为选项
async function initFilters() {
  const catSelect = document.getElementById("category-select");
  const difSelect = document.getElementById("difficulty-select");
  if (!catSelect && !difSelect) return;
  try {
    const all = await api("/questions", "GET");
    const categories = [];
    const difficulties = [];
    all.forEach(function (q) {
      if (q.category && categories.indexOf(q.category) === -1) {
        categories.push(q.category);
      }
      if (q.difficulty && difficulties.indexOf(q.difficulty) === -1) {
        difficulties.push(q.difficulty);
      }
    });
    categories.forEach(function (c) {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      catSelect.appendChild(opt);
    });
    difficulties.forEach(function (d) {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      difSelect.appendChild(opt);
    });
  } catch (e) {
    // 选项加载失败不影响题目列表展示
  }
}

// 题库分页状态：当前页码与每页条数（只有题库页使用 loadQuestions）
let bankPage = 1;
const bankPageSize = 10;

// 搜索/筛选条件变化时回到第 1 页再重新加载
function resetAndLoadQuestions() {
  bankPage = 1;
  loadQuestions();
}

// 上一页/下一页：页码最小为 1
function changeBankPage(delta) {
  bankPage = Math.max(1, bankPage + delta);
  loadQuestions();
}

// 拉取题目并渲染成手风琴列表（题库页使用，支持搜索、筛选与分页）
async function loadQuestions() {
  const container = document.getElementById("question-list");
  container.textContent = "加载中……";
  try {
    // 读取页面上的搜索框和下拉筛选条件，拼接到查询地址后面
    const params = new URLSearchParams();
    const searchInput = document.getElementById("search-input");
    const catSelect = document.getElementById("category-select");
    const difSelect = document.getElementById("difficulty-select");
    if (searchInput && searchInput.value.trim()) {
      params.append("q", searchInput.value.trim());
    }
    if (catSelect && catSelect.value) {
      params.append("category", catSelect.value);
    }
    if (difSelect && difSelect.value) {
      params.append("difficulty", difSelect.value);
    }
    // 分页参数：每页 bankPageSize 条，第 bankPage 页从 (bankPage-1)*bankPageSize 条开始取
    params.append("limit", String(bankPageSize));
    params.append("offset", String((bankPage - 1) * bankPageSize));
    const url = "/questions?" + params.toString();
    // 用 apiMeta 拿响应头里的 X-Total-Count（筛选后的总题目数），计算总页数
    const result = await apiMeta(url, "GET");
    const questions = result.data;
    const total = parseInt(result.headers.get("X-Total-Count") || String(questions.length), 10);
    const totalPages = Math.max(1, Math.ceil(total / bankPageSize));
    // 更新题库页右上角的题目数量徽章（页面没有该元素时跳过）
    const countEl = document.getElementById("question-count");
    if (countEl) {
      countEl.textContent = "共 " + total + " 道题";
    }
    container.textContent = "";
    // 分页条：上一页 / 第 x / y 页 / 下一页
    const pager = document.createElement("div");
    pager.className = "d-flex justify-content-center align-items-center gap-2 mb-2";
    const prevBtn = document.createElement("button");
    prevBtn.className = "btn btn-sm btn-outline-secondary";
    prevBtn.type = "button";
    prevBtn.textContent = "上一页";
    prevBtn.disabled = bankPage <= 1;
    prevBtn.onclick = function () { changeBankPage(-1); };
    const pageInfo = document.createElement("span");
    pageInfo.className = "small text-muted";
    pageInfo.textContent = "第 " + bankPage + " / " + totalPages + " 页";
    const nextBtn = document.createElement("button");
    nextBtn.className = "btn btn-sm btn-outline-secondary";
    nextBtn.type = "button";
    nextBtn.textContent = "下一页";
    nextBtn.disabled = bankPage >= totalPages;
    nextBtn.onclick = function () { changeBankPage(1); };
    pager.appendChild(prevBtn);
    pager.appendChild(pageInfo);
    pager.appendChild(nextBtn);
    container.appendChild(pager);
    if (questions.length === 0) {
      // 页码越界等情况：回退一页重试一次，避免停留在空白页
      if (bankPage > 1) {
        changeBankPage(-1);
        return;
      }
      const tip = document.createElement("div");
      tip.className = "alert alert-warning mb-0";
      tip.textContent = "没有找到符合条件的题目，试试调整搜索或筛选条件";
      container.appendChild(tip);
      return;
    }
    questions.forEach(function (q, index) {
      // 手风琴容器
      const item = document.createElement("div");
      item.className = "accordion-item";

      const head = document.createElement("h2");
      head.className = "accordion-header";

      const button = document.createElement("button");
      button.className = "accordion-button collapsed";
      button.type = "button";
      button.setAttribute("data-bs-toggle", "collapse");
      button.setAttribute("data-bs-target", "#q-" + q.id);
      button.textContent = q.title;

      // 标题前加题目 ID 编号徽章，方便对照答题记录里的题号
      const idTag = document.createElement("span");
      idTag.className = "badge bg-secondary me-2";
      idTag.textContent = "ID " + q.id;
      button.prepend(idTag);

      const badge = document.createElement("span");
      badge.className = "badge ms-2 " + difficultyColor(q.difficulty);
      badge.textContent = q.difficulty;
      button.appendChild(badge);

      head.appendChild(button);
      item.appendChild(head);

      // 手风琴展开区：分类 + 答案
      const wrapper = document.createElement("div");
      wrapper.id = "q-" + q.id;
      wrapper.className = "accordion-collapse collapse";
      wrapper.setAttribute("data-bs-parent", "#question-list");

      const body = document.createElement("div");
      body.className = "accordion-body";
      const category = document.createElement("p");
      category.className = "text-muted small mb-1";
      category.textContent = "分类：" + q.category;
      body.appendChild(category);

      // 显示本题标签（没有标签时跳过）
      if (q.tags) {
        const tagsLine = document.createElement("p");
        tagsLine.className = "text-muted small mb-1";
        tagsLine.textContent = "标签：" + q.tags;
        body.appendChild(tagsLine);
      }

      // 参考答案默认隐藏，点按钮再显示
      const toggleBtn = document.createElement("button");
      toggleBtn.className = "btn btn-sm btn-link p-0 mb-1";
      toggleBtn.type = "button";
      toggleBtn.textContent = "显示答案";
      const answerWrap = document.createElement("div");
      answerWrap.className = "mb-1";
      answerWrap.style.display = "none";
      const answer = document.createElement("p");
      answer.className = "mb-0";
      answer.textContent = "答案：" + q.answer;
      answerWrap.appendChild(answer);
      toggleBtn.onclick = function () {
        if (answerWrap.style.display === "none") {
          answerWrap.style.display = "block";
          toggleBtn.textContent = "隐藏答案";
        } else {
          answerWrap.style.display = "none";
          toggleBtn.textContent = "显示答案";
        }
      };
      body.appendChild(toggleBtn);
      body.appendChild(answerWrap);

      // 作答区：写答案提交给 AI 批改
      const input = document.createElement("textarea");
      input.className = "form-control form-control-sm";
      input.id = "ans-" + q.id;
      input.rows = 2;
      input.placeholder = "写下你的答案，提交给 AI 批改";
      const submitBtn = document.createElement("button");
      submitBtn.className = "btn btn-sm btn-outline-primary mt-1";
      submitBtn.type = "button";
      submitBtn.textContent = "提交答案";
      submitBtn.onclick = function () { submitAnswer(q.id); };
      const result = document.createElement("div");
      result.id = "grade-" + q.id;
      result.className = "small mt-1";
      body.appendChild(input);
      body.appendChild(submitBtn);
      body.appendChild(result);

      wrapper.appendChild(body);

      item.appendChild(wrapper);
      container.appendChild(item);
    });
    // 外层容器需要 accordion 样式类（默认无样式时手动加上）
    if (!container.classList.contains("accordion")) {
      container.classList.add("accordion");
    }
  } catch (e) {
    container.textContent = "加载失败：" + e.message;
  }
}

// 提交本题答案给 AI 批改，并展示评分与点评
async function submitAnswer(qid) {
  const input = document.getElementById("ans-" + qid);
  const result = document.getElementById("grade-" + qid);
  const answer = input.value.trim();
  if (answer === "") {
    result.className = "small mt-1 text-danger";
    result.textContent = "请先输入你的答案";
    return;
  }
  result.className = "small mt-1";
  result.textContent = "AI 批改中……";
  try {
    // 已登录时把 user_id 一起提交，让答题记录归属当前用户
    const user = currentUser();
    const body = { question_id: qid, answer: answer };
    if (user) body.user_id = user.id;
    const data = await api("/grade", "POST", body);
    result.className = "small mt-1 " + (data.correct === 1 ? "text-success" : "text-danger");
    result.textContent = "评分：" + data.score + "｜" + (data.correct === 1 ? "正确" : "错误") + "｜点评：" + data.comment;
  } catch (e) {
    result.className = "small mt-1 text-danger";
    result.textContent = "批改失败：" + e.message;
  }
}

// 页面打开时恢复导航栏登录态
showUser();