import re

# --------- 测试 ----------
text1 = "com@【AI增强】EDMo如果你只想匹配特定关键词"
print(remove_by_wildcard(text1, "@*"))  # 输出: "com"
print(remove_by_wildcard(text1, "*EDMo"))  # 输出: "com@【AI增强】如果你只想匹配特定关键词"
print(remove_by_wildcard(text1, "【*】"))  # 输出: "com@EDMo如果你只想匹配特定关键词"
print(remove_by_wildcard(text1, "*增强*"))  # 输出: "com@【】EDMo如果你只想匹配特定关键词"
