package com.ruoyi.web.controller.system;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.system.service.ISysUserService;
import com.ruoyi.system.service.DemoAccountService;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/system/user")
public class SysUserController extends BaseController {
 private final ISysUserService users; private final DemoAccountService accounts;
 public SysUserController(ISysUserService users, DemoAccountService accounts) {this.users=users;this.accounts=accounts;}
 @GetMapping("/list") public TableDataInfo list(SysUser user) {startPage();return getDataTable(users.selectUserList(user));}
 @DeleteMapping("/{id}") @Log(title="删除账号", businessType=BusinessType.DELETE)
 public AjaxResult delete(@PathVariable Long id) {return toAjax(accounts.delete(id));}
 @PostMapping @Log(title="账号管理", businessType=BusinessType.INSERT,isSaveRequestData=false,isSaveResponseData=false)
 public AjaxResult create(@RequestBody SysUser user) {return toAjax(accounts.create(user));}
 @PutMapping("/changeStatus") @Log(title="账号状态", businessType=BusinessType.UPDATE)
 public AjaxResult status(@RequestBody SysUser user) {return toAjax(accounts.status(user.getUserId(),user.getStatus()));}
 @PutMapping("/resetPwd") @Log(title="重置密码", businessType=BusinessType.UPDATE,isSaveRequestData=false,isSaveResponseData=false)
 public AjaxResult password(@RequestBody SysUser user) {return toAjax(accounts.password(user.getUserId(),user.getPassword()));}
}
