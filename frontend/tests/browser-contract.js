// 在已授权的 browser-use 会话中，传入已登录且位于库存页的 tab。
// 回归：min=0.01 而 step 默认为1时，默认金额1.00被原生HTML表单拒绝。
// 验证实际 DOM validity，而不是检查 Vue 源码字符串。
export async function verifyPriceForm(tab) {
  await tab.playwright.getByRole('button', { name: '＋ 新增商品', exact: true }).click()
  const input = tab.playwright.getByRole('spinbutton', { name: '单价（元）', exact: true })
  for (const price of ['1.00', '12.34', '0.01', '99999999.99']) {
    await input.fill(price)
    const state = await input.evaluate(el => ({ value: el.value, valid: el.validity.valid, stepMismatch: el.validity.stepMismatch }))
    if (!state.valid || state.stepMismatch) throw new Error(`合法金额被浏览器拒绝: ${JSON.stringify(state)}`)
  }
  await tab.playwright.getByRole('button', { name: '取消', exact: true }).click()
  return { tested: ['1.00', '12.34', '0.01', '99999999.99'], passed: true }
}
