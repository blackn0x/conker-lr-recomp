/* setenv / unsetenv for MinGW (the C runtime only has _putenv_s). */
#ifndef XBOXRECOMP_MINGW_ENV_H
#define XBOXRECOMP_MINGW_ENV_H
#if defined(_WIN32) && !defined(_MSC_VER)
#include <stdlib.h>
static inline int setenv(const char *name, const char *value, int overwrite)
{
    if (!overwrite && getenv(name))
        return 0;
    return _putenv_s(name, value);
}
static inline int unsetenv(const char *name)
{
    return _putenv_s(name, "");      /* an empty value removes the variable */
}
#endif
#endif
