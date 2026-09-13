#!/usr/bin/env ruby
# Resuelve y descarga los pods de un proyecto Flutter con el Resolver/Analyzer de
# CocoaPods y vuelca el grafo normalizado a JSON. No genera Pods.xcodeproj: los
# flags salen del xcconfig que CocoaPods calcula para cada PodTarget, que es la
# misma fuente que usaria Xcode.
#
#   ruby 20-podgraph.rb /root/App /out/podgraph.json
# CocoaPods normaliza Unicode sobre Dir.pwd; sin locale UTF-8 revienta.
if Encoding.default_external != Encoding::UTF_8
  ENV['LANG'] = ENV['LC_ALL'] = 'C.UTF-8'
  exec(RbConfig.ruby, __FILE__, *ARGV)
end

require 'cocoapods'
require 'json'
require 'fileutils'

project  = ARGV[0] or abort "uso: 20-podgraph.rb <proyecto> [salida.json]"
outfile  = ARGV[1] || '/out/podgraph.json'
ios_dir  = File.join(project, 'ios')

# El minimo sale de MIN_OS, no del Podfile: si cada sitio trae el suyo acabas con
# los pods compilados para una version y la app declarando otra.
podfile_path = File.join(ios_dir, 'Podfile')
platform_version = ENV['MIN_OS']
if platform_version.nil? || platform_version.empty?
  platform_version =
    if File.exist?(podfile_path) && (m = File.read(podfile_path).match(/platform\s+:ios,\s*'([\d.]+)'/))
      m[1]
    else
      '16.0'
    end
end

# Los plugins declaran dependency 'Flutter'; el engine lo aporta hatch, asi que
# basta un podspec vacio para que el resolver cierre.
stub = File.join(project, '.hatch', 'FlutterStub')
FileUtils.mkdir_p(stub)
File.write(File.join(stub, 'Flutter.podspec'), <<~SPEC)
  Pod::Spec.new do |s|
    s.name     = 'Flutter'
    s.version  = '1.0.0'
    s.summary  = 'Flutter engine'
    s.homepage = 'https://flutter.dev'
    s.license  = { :type => 'BSD' }
    s.authors  = 'Flutter'
    s.source   = { :http => 'https://flutter.dev' }
    s.ios.deployment_target = '12.0'
    s.vendored_frameworks = 'path/to/nothing'
  end
SPEC

# Los podspecs de los plugins usan rutas relativas que dan por hecho el arbol
# ios/.symlinks/plugins/<plugin> que monta el podhelper de Flutter (firebase_core
# busca asi el firebase_sdk_version.rb de su hermano).
links = File.join(ios_dir, '.symlinks', 'plugins')
FileUtils.mkdir_p(links)

deps = JSON.parse(File.read(File.join(project, '.flutter-plugins-dependencies')))
pods, swiftpm = [], []
(deps.dig('plugins', 'ios') || []).each do |p|
  name, path = p['name'], p['path'].chomp('/')
  link = File.join(links, name)
  FileUtils.rm_f(link)
  File.symlink(path, link)
  if (d = ['ios', 'darwin'].find { |sub| File.exist?(File.join(path, sub, "#{name}.podspec")) })
    pods << [name, File.join(link, d)]
  elsif (d = ['ios', 'darwin'].find { |sub| File.exist?(File.join(path, sub, name, 'Package.swift')) })
    swiftpm << [name, File.join(path, d, name)]
  else
    warn "!! #{name}: ni podspec ni Package.swift en #{path}"
  end
end

podfile = Pod::Podfile.new(Pathname.new(podfile_path)) do
  install! 'cocoapods', :integrate_targets => false,
                        :skip_pods_project_generation => true,
                        :deterministic_uuids => false,
                        :warn_for_multiple_pod_sources => false
  platform :ios, platform_version
  use_frameworks! :linkage => :static
  use_modular_headers!
  target 'Runner' do
    pod 'Flutter', :path => stub
    pods.each { |n, d| pod n, :path => d }
  end
end

sandbox   = Pod::Sandbox.new(File.join(ios_dir, 'Pods'))
installer = Pod::Installer.new(sandbox, podfile, nil)
installer.repo_update = false
installer.update      = false
begin
  installer.install!
rescue Molinillo::VersionConflict, Pod::Informative => e
  msg = e.message
  if msg =~ /deployment target|platform|compatible versions/i
    warn "
!! CocoaPods no pudo resolver con iOS #{platform_version}."
    warn "!! Suele ser un pod que exige un minimo mayor: sube MIN_OS en app.env."
  end
  raise
end

# El arbol Headers/Public al que apuntan los HEADER_SEARCH_PATHS lo monta
# CocoaPods junto con el proyecto; sin proyecto hay que pedirlo a mano.
if Dir.glob(File.join(sandbox.public_headers.root, '*')).empty? &&
   defined?(Pod::Installer::SandboxHeaderPathsInstaller)
  Pod::Installer::SandboxHeaderPathsInstaller.new(sandbox, installer.pod_targets).install!
end

def xcconfig_of(t)
  bs = t.build_settings
  s  = bs.is_a?(Hash) ? (bs['Release'] || bs.values.first) : bs
  s ? s.xcconfig.to_hash : {}
rescue => e
  { '_error' => e.message }
end

def plist_of(t)
  t.file_accessors.flat_map { |fa| fa.spec_consumer.spec.attributes_hash['script_phases'] || [] }
end

targets = installer.pod_targets.map do |t|
  accessors = t.file_accessors.map do |fa|
    sc = fa.spec_consumer
    {
      'spec'                => fa.spec.name,
      'arc_source_files'    => fa.arc_source_files.map(&:to_s),
      'non_arc_source_files'=> fa.non_arc_source_files.map(&:to_s),
      'public_headers'      => fa.public_headers.map(&:to_s),
      'private_headers'     => fa.private_headers.map(&:to_s),
      'headers'             => fa.headers.map(&:to_s),
      'vendored_frameworks' => fa.vendored_frameworks.map(&:to_s),
      'vendored_libraries'  => fa.vendored_libraries.map(&:to_s),
      'resources'           => fa.resources.map(&:to_s),
      'resource_bundles'    => (fa.resource_bundles || {}).map { |k, v| [k, Array(v).map(&:to_s)] }.to_h,
      'module_map'          => fa.module_map&.to_s,
      'frameworks'          => sc.frameworks,
      'weak_frameworks'     => sc.weak_frameworks,
      'libraries'           => sc.libraries,
      'compiler_flags'      => sc.compiler_flags,
      'requires_arc'        => sc.requires_arc,
      'header_dir'          => sc.header_dir,
      'header_mappings_dir' => sc.header_mappings_dir,
      'pod_target_xcconfig' => sc.pod_target_xcconfig,
    }
  end
  {
    'name'              => t.name,
    'pod_name'          => t.pod_name,
    'module_name'       => t.product_module_name,
    'uses_swift'        => t.uses_swift?,
    'swift_version'     => t.swift_version.to_s,
    'defines_module'    => t.defines_module?,
    'deployment_target' => t.platform.deployment_target.to_s,
    'dependencies'      => t.dependent_targets.map(&:name),
    'srcroot'           => sandbox.pod_dir(t.pod_name).to_s,
    'specs'             => t.specs.map(&:name),
    'script_phases'     => plist_of(t),
    'xcconfig'          => xcconfig_of(t),
    'file_accessors'    => accessors,
  }
end

File.write(outfile, JSON.pretty_generate(
  'project'            => project,
  'ios_deployment'     => platform_version,
  'pods_root'          => sandbox.root.to_s,
  'public_headers_root'=> sandbox.public_headers.root.to_s,
  'swiftpm_plugins'    => swiftpm.map { |n, d| { 'name' => n, 'path' => d } },
  'targets'            => targets))

puts "#{targets.size} pod targets -> #{outfile}"
puts "swiftpm: #{swiftpm.map(&:first).join(', ')}" unless swiftpm.empty?
