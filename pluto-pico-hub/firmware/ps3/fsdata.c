/* CPC stub: empty lwIP httpd filesystem.
 *
 * The GP2040-CE web-config UI is intentionally not built (SKIP_WEBBUILD=TRUE);
 * this controller is driven and configured entirely via the UartInput addon.
 * httpd still links and runs, it simply serves no files. fs.c #includes this
 * file and the only symbol it references is FS_ROOT (an empty list = NULL).
 *
 * Goes to lib/httpd/fsdata.c in the GP2040-CE tree.
 */
#define FS_ROOT NULL
#define FS_NUMFILES 0
typedef int cpc_httpd_fsdata_stub;
