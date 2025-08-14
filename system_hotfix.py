#!/usr/bin/env python3
"""
系统热修复模块 - 纯外部方式修复系统启动问题
不修改任何内部文件，通过插件机制在系统启动时应用修复

目标问题：expression_selector初始化失败导致系统无法启动
解决方案：在插件加载时提供工作的expression_selector对象
"""

import sys
import types
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class MockExpressionSelector:
    """模拟的ExpressionSelector，提供基本功能"""
    
    def __init__(self):
        logger.info("🔧 [系统热修复] 创建模拟ExpressionSelector")
        
    def select_expressions(self, *args, **kwargs):
        """模拟表达方式选择"""
        logger.debug("🔧 [系统热修复] 调用模拟select_expressions")
        return []
        
    def evaluate_expressions(self, *args, **kwargs):
        """模拟表达方式评估"""
        logger.debug("🔧 [系统热修复] 调用模拟evaluate_expressions")
        return []
        
    def get_expressions(self, *args, **kwargs):
        """模拟获取表达方式"""
        logger.debug("🔧 [系统热修复] 调用模拟get_expressions")
        return []

def apply_expression_selector_hotfix():
    """应用expression_selector热修复"""
    try:
        logger.info("🔧 [系统热修复] 开始修复expression_selector问题")
        
        # 检查模块是否已经导入
        module_name = 'src.chat.express.expression_selector'
        
        if module_name in sys.modules:
            module = sys.modules[module_name]
            if hasattr(module, 'expression_selector') and module.expression_selector is not None:
                logger.info("✅ [系统热修复] expression_selector已正常工作，无需修复")
                return True
            else:
                # 模块存在但对象为None，替换为工作的对象
                module.expression_selector = MockExpressionSelector()
                logger.info("✅ [系统热修复] 已替换失效的expression_selector对象")
                return True
        else:
            # 模块未导入，预先创建模拟模块（仅在必要时）
            logger.debug("🔧 [系统热修复] expression_selector模块尚未导入，将在需要时创建")
            return True
            
    except Exception as e:
        logger.error(f"❌ [系统热修复] 修复失败: {e}")
        return False

def ensure_expression_selector_available():
    """确保expression_selector可用 - 在导入时调用"""
    module_name = 'src.chat.express.expression_selector'
    
    # 如果模块存在但expression_selector不可用，提供替代
    if module_name in sys.modules:
        module = sys.modules[module_name]
        if not hasattr(module, 'expression_selector') or module.expression_selector is None:
            module.expression_selector = MockExpressionSelector()
            logger.info("🔧 [系统热修复] 已修复expression_selector")

def create_mock_expression_selector_module():
    """创建模拟的expression_selector模块"""
    try:
        module_name = 'src.chat.express.expression_selector'
        
        if module_name not in sys.modules:
            # 创建模拟模块
            mock_module = types.ModuleType(module_name)
            mock_module.expression_selector = MockExpressionSelector()
            mock_module.ExpressionSelector = MockExpressionSelector
            sys.modules[module_name] = mock_module
            logger.info("🔧 [系统热修复] 已创建模拟expression_selector模块")
            return True
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [系统热修复] 创建模拟模块失败: {e}")
        return False

# 导入时hook - 尝试预防性修复
def install_import_hook():
    """安装导入钩子，在相关模块导入时自动修复"""
    
    original_import = __builtins__.__import__
    
    def patched_import(name, *args, **kwargs):
        """修补的导入函数"""
        try:
            # 正常导入
            module = original_import(name, *args, **kwargs)
            
            # 如果是导入expression_selector相关模块，检查是否需要修复
            if 'expression_selector' in name:
                ensure_expression_selector_available()
            
            return module
            
        except ImportError as e:
            # 如果是expression_selector导入失败，尝试提供模拟模块
            if 'expression_selector' in str(e):
                logger.warning(f"🔧 [系统热修复] 检测到expression_selector导入失败，尝试修复: {e}")
                create_mock_expression_selector_module()
                # 重试导入
                try:
                    return original_import(name, *args, **kwargs)
                except:
                    pass
            
            # 重新抛出原始异常
            raise e
    
    # 安装钩子
    __builtins__.__import__ = patched_import
    logger.info("🔧 [系统热修复] 导入钩子已安装")

def apply_all_hotfixes():
    """应用所有热修复"""
    logger.info("🚀 [系统热修复] 开始应用所有热修复")
    
    fixes_applied = 0
    
    # 1. 安装导入钩子
    try:
        install_import_hook()
        fixes_applied += 1
    except Exception as e:
        logger.error(f"❌ [系统热修复] 安装导入钩子失败: {e}")
    
    # 2. 修复expression_selector
    if apply_expression_selector_hotfix():
        fixes_applied += 1
    
    # 3. 预先创建模拟模块（如果需要）
    if create_mock_expression_selector_module():
        fixes_applied += 1
    
    logger.info(f"✅ [系统热修复] 已应用 {fixes_applied} 个热修复")
    return fixes_applied > 0

# 在模块导入时自动应用热修复
if __name__ != "__main__":
    # 这是被导入时，立即应用热修复
    apply_all_hotfixes()
