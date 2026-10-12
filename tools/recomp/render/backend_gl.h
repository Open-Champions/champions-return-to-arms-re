// backend_gl.h - the OpenGL backend (backend_gl.cpp).  Make it, and call it, with an
// OpenGL 4.1 core (or newer) context current.
#pragma once
#include "backend.h"

namespace render {

class GlBackend : public Backend {
  public:
    GlBackend();
    ~GlBackend() override;
    void set_output_size(int width, int height) override;
    void execute(const FrameList& frame) override;
    void present(int width, int height, double aspect) override;
    bool read_shown(std::vector<uint8_t>& rgba, int& width, int& height) override;
    bool read_target(uint32_t id, std::vector<uint8_t>& rgba, int& width, int& height);
    uint64_t draw_calls() const;

  private:
    struct Impl;
    Impl* impl;
};

}  // namespace render
