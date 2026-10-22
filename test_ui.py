import time
import pytest
from playwright.sync_api import expect

# 系统测试（UI 自动化）：用真实浏览器访问运行中的项目，模拟用户操作验证页面行为
# 全部用例走浏览器真实 HTTP 请求，不依赖大模型接口与密钥
# 运行方式：conda run -n ctfd python -m pytest test_ui.py -q --alluredir=allure-results

def test_ui_root(page, server):
    # 主页应正常打开，显示项目名称与 AI 问答输入框
    page.goto(server + "/", wait_until="domcontentloaded")
    expect(page.locator(".navbar-brand")).to_have_text("AI 智能面试助手")
    expect(page.locator("#chat-input")).to_be_visible()

def test_ui_question_bank(page, server):
    # 题库页：搜索框与筛选下拉可见，题目列表异步加载完成（计数徽章不再是 0）
    page.goto(server + "/bank", wait_until="domcontentloaded")
    expect(page.locator("#search-input")).to_be_visible()
    expect(page.locator("#category-select")).to_be_visible()
    expect(page.locator("#question-count")).not_to_have_text("共 0 道题", timeout=10000)
    expect(page.locator("#question-list > *").first).to_be_visible(timeout=10000)

def test_ui_register_login_flow(page, server):
    # 完整用户流程：注册新账号 → 自动跳登录页 → 登录成功跳回主页 → 右上角显示当前用户、登录按钮隐藏
    username = "ui_" + str(int(time.time() * 1000))
    password = "ui123456"
    page.goto(server + "/register", wait_until="domcontentloaded")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#register-button")
    expect(page).to_have_url(server + "/login", timeout=10000)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#login-button")
    expect(page).to_have_url(server + "/", timeout=10000)
    expect(page.locator("#user-info")).to_contain_text("当前用户：" + username)
    expect(page.locator("#nav-login")).to_be_hidden()

def test_ui_login_wrong_password(page, server):
    # 错误密码登录：页面内出现红色「登录失败」提示条，不跳转
    page.goto(server + "/login", wait_until="domcontentloaded")
    page.fill("#username", "不存在的用户_" + str(int(time.time() * 1000)))
    page.fill("#password", "wrongpass")
    page.click("#login-button")
    tip = page.locator("#login-tip")
    expect(tip).to_be_visible(timeout=10000)
    expect(tip).to_contain_text("登录失败")

@pytest.mark.parametrize("path", ["/stats", "/records", "/profile"])
def test_ui_auth_guard_redirect(page, server, path):
    # 未登录直接访问个人数据页：requireAuth 守卫自动跳转到登录页
    page.goto(server + path, wait_until="domcontentloaded")
    expect(page).to_have_url(server + "/login", timeout=10000)