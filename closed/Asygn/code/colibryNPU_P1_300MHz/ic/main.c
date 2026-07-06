#include "colibry_drivers.h"
#include "api/internally_implemented.h"
#include "api/submitter_implemented.h"


int main() {
  COLIBRY_DRIVERS_INIT();
  ee_benchmark_initialize();
  while (1) {
    int c;
    c = th_getchar();
    ee_serial_callback(c);
  }
  return 0;
}
