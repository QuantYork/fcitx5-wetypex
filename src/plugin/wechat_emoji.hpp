#pragma once
#include "../common/wechat_emoticons.hpp"
#include <fontconfig/fontconfig.h>

namespace wetype_emoji {
inline bool originalFontAvailable() {
  FcInitBringUptoDate();
  auto *pattern = FcPatternCreate();
  if (!pattern)
    return false;
  FcPatternAddString(
      pattern, FC_FAMILY,
      reinterpret_cast<const FcChar8 *>(wetype::WeChatEmoticons::FontFamily));
  FcConfigSubstitute(nullptr, pattern, FcMatchPattern);
  FcDefaultSubstitute(pattern);
  FcResult result;
  auto *match = FcFontMatch(nullptr, pattern, &result);
  FcPatternDestroy(pattern);
  if (!match)
    return false;
  FcChar8 *family = nullptr;
  FcCharSet *characters = nullptr;
  FcBool colour = FcFalse;
  const bool available =
      FcPatternGetString(match, FC_FAMILY, 0, &family) == FcResultMatch &&
      std::string(reinterpret_cast<const char *>(family)) ==
          wetype::WeChatEmoticons::FontFamily &&
      FcPatternGetCharSet(match, FC_CHARSET, 0, &characters) == FcResultMatch &&
      FcCharSetHasChar(characters, 0x10f000) &&
      FcPatternGetBool(match, FC_COLOR, 0, &colour) == FcResultMatch && colour;
  FcPatternDestroy(match);
  return available;
}
} // namespace wetype_emoji
