#!/usr/bin/env python

from io import StringIO

import numpy as np
from parmed.topologyobjects import DihedralTypeList
from ost.interfaces.parmed import ParmEdStructure


class LAMMPSStructure(ParmEdStructure):
    HeadLmpInput = """
units real
atom_style full

dimension 3
boundary {pbc:} #p p m

bond_style hybrid harmonic
angle_style hybrid harmonic
dihedral_style hybrid {dihedralstyle:}
# special_bonds amber # same as special_bonds lj 0.0 0.0 0.5000 coul 0.0 0.0 0.83333
special_bonds amber lj 0.0 0.0 0.50000 coul 0.0 0.0 0.83333 angle yes dihedral no
box tilt large

read_data {dat:}

neighbor {cutoff_skin:} multi
neigh_modify every 2 delay 4 check yes
#neigh_modify every 2 delay 10

{pair_ljcoul:}
pair_modify mix arithmetic shift no tail yes
kspace_style pppm {ewald_error_tolerance:}
kspace_modify gewald {gewald:} mesh {fftx:} {ffty:} {fftz:} order 6

"""

    TailLmpInput = """
#pair_modify mix arithmetic
thermo_style custom step temp vol press etotal pe ke epair ecoul elong evdwl ebond eangle edihed eimp emol etail \
#    cella cellb cellc cellalpha cellbeta cellgamma density pxx pyy pzz pxy pxy pyz
thermo_modify lost ignore flush yes

#compute peatom all pe/atom
#dump 1 all custom 1 dump.lammpstrj id type q x y z fx fy fz c_peatom element
#dump_modify 1 sort id pad 9 element {eles:}
variable ele_string string "{eles:}"

#minimize 1e-5 1e-5 100 100
#run 0

"""
    _progname = "LAMMPS"
    _dihedralstyle = "charmm"

    @property
    def atomtypes_with_resname(self):
        if not hasattr(self, "_atomtype_with_resname"):
            ps = self.get_parameterset_with_resname_as_prefix()
            self._atomtypes_with_resname = ps.atom_types
        return self._atomtypes_with_resname

    def set_charmm_style_lj(self):
        self.ljmode = "charmmfsw"

    @property
    def pair_ljcoul(self):
        if hasattr(self, "ljmode") and self.ljmode == "charmmfsw":
            return f"pair_style lj/{self.ljmode}/coul/long {self.cutoff_ljin} {self.cutoff_ljout} {self.cutoff_coul}"
        else:
            return f"pair_style lj/cut/coul/long {self.cutoff_ljout} {self.cutoff_coul}"

    def _write_input(self, of, fdat):
        """
        Write LMP input files
        of: output file
        fdat: lammps dat file path
        ljmode: cut or charmmfsw
        """
        if len(self.title) > 0:
            of.write("#smiles: {:s}".format(self.title))
        else:
            of.write("# generated by ost")
        fftx, ffty, fftz = self.fftgrid
        pbc_string = ''
        slab = False
        for p in self.pbc:
            if p:
                pbc_string += 'p '
            else:
                pbc_string += 'f '
                slab = True
        head = self.HeadLmpInput.format(
            pbc=pbc_string,
            dihedralstyle=self._dihedralstyle,
            dat=fdat,
            cutoff_skin=self.cutoff_skin,
            pair_ljcoul=self.pair_ljcoul,
            ewald_error_tolerance=self.ewald_error_tolerance,
            gewald=self.gewald,
            fftx=fftx,
            ffty=ffty,
            fftz=fftz,
        )
        if len(self.bonds) == 0:
            head = head.replace("bond_style ", "#bond_style ")
        if len(self.angles) == 0:
            head = head.replace("angle_style ", "#angle_style ")
        if len(self.dihedrals) == 0:
            head = head.replace("dihedral_style ", "#dihedral_style ")
        of.write(head)
        if slab:
            of.write('kspace_modify slab 3.0\n')

        for i, (_k, t) in enumerate(self.atomtypes_with_resname.items(), 1):
            line = "pair_coeff {0:d} {0:d} {1:11.7f} {2:11.7f}\n".format(i, t.epsilon, t.sigma)
            of.write(line)
        of.write(self.TailLmpInput.format(eles=" ".join(self.get_element_list())))

    def _write_dat_head(self, of):
        of.write("\n")
        of.write("%d atoms\n" % (len(self.atoms)))
        if len(self.bonds) >= 0:
            of.write("%d bonds\n" % (len(self.bonds)))
        of.write("%d angles\n" % (len(self.angles)))
        of.write("%d dihedrals\n" % (len(self.dihedrals)))
        of.write("%d impropers\n" % (0))
        of.write("\n")
        of.write("%d atom types\n" % (len(self.atomtypes_with_resname)))
        of.write("%d bond types\n" % (len(self.bond_types)))
        of.write("%d angle types\n" % (len(self.angle_types)))
        of.write("%d dihedral types\n" % (len(self.dihedral_types)))
        of.write("\n")

    def _write_dat_box(self, of, orthogonality=False, padding=[0, 0, 0]):
        """
        Args:
            orthogonality: whether or not impose orthogonality
        """
        if self.box is not None:
            xlo = ylo = zlo = 0.0
            a = self.box[0]
            b = self.box[1]
            c = self.box[2]
            alp = np.radians(self.box[3])
            bet = np.radians(self.box[4])
            gam = np.radians(self.box[5])
            xhi = a
            xy = b * np.cos(gam)
            xz = c * np.cos(bet)
            yhi = (b**2 - xy**2) ** 0.5
            yz = (b * c * np.cos(alp) - xy * xz) / yhi
            zhi = (c**2 - xz**2 - yz**2) ** 0.5
            if c**2 - xz**2 - yz**2 < 0:
                print("bad lattice angle condition: alpha, beta, gamma = {}, {}, {}".format(alp, bet, gam))
                raise
            of.write("%9.4f %9.4f xlo xhi\n" % (xlo-padding[0], xhi+padding[0]))
            of.write("%9.4f %9.4f ylo yhi\n" % (ylo-padding[1], yhi+padding[1]))
            of.write("%9.4f %9.4f zlo zhi\n" % (zlo-padding[2], zhi+padding[0]))

            if not orthogonality:
                of.write("%9.4f %9.4f %9.4f xy xz yz\n" % (xy, xz, yz))
            else:
                of.write("#%9.4f %9.4f %9.4f xy xz yz\n" % (xy, xz, yz))

        else:
            xl, yl, zl = self.LARGEBOX[:3]
            xlo = -0.5 * xl
            xhi = 0.5 * xl
            ylo = -0.5 * yl
            yhi = 0.5 * yl
            zlo = -0.5 * zl
            zhi = 0.5 * zl
            of.write("%9.4f %9.4f xlo xhi\n" % (xlo, xhi))
            of.write("%9.4f %9.4f ylo yhi\n" % (ylo, yhi))
            of.write("%9.4f %9.4f zlo zhi\n" % (zlo, zhi))
            of.write("%9.4f %9.4f %9.4f xy xz yz\n" % (0, 0, 0))
        of.write("\n")

    def _write_data(self, of, orthogonality=False, padding=[0, 0, 0]):
        """Write LAMMPS data files"""
        if len(self.title) > 0:
            of.write("#smiles: {:s}\n".format(self.title))
        else:
            of.write("#generated by xtalmol\n")
        self._write_dat_head(of)
        self._write_dat_box(of, orthogonality, padding)

        of.write("Masses\n")
        of.write("\n")
        for i, (name, t) in enumerate(self.atomtypes_with_resname.items(), 1):
            of.write("%d %11.7f #%s\n" % (i, t.mass, name))
        of.write("\n")

        # write parameters

        if len(self.bond_types) > 0:
            of.write("Bond Coeffs\n")
            of.write("\n")
            for i, t in enumerate(self.bond_types, 1):
                tags = self._get_tags(t, self.bonds)
                if len(tags) > 20: tags = tags[:20]
                of.write("%d harmonic %11.7f %11.7f #%s\n" % (i, t.k, t.req, tags))
            of.write("\n")
        if len(self.angle_types) > 0:
            of.write("Angle Coeffs\n")
            of.write("\n")
            for i, t in enumerate(self.angle_types, 1):
                tags = self._get_tags(t, self.angles)
                if len(tags) > 20: tags = tags[:20]
                of.write("%d harmonic %11.7f %11.7f #%s\n" % (i, t.k, t.theteq, tags))
            of.write("\n")
        if len(self.dihedral_types) > 0:
            of.write("Dihedral Coeffs\n")
            of.write("\n")
            if self._dihedralstyle == "fourier":
                for i, ts in enumerate(self.dihedral_types, 1):
                    tags = self._get_tags(ts, self.dihedrals)
                    if len(tags) > 20: tags = tags[:20]
                    string = "%d fourier %d" % (i, len(ts))
                    for t in ts:
                        string += " %f %d %f" % (t.phi_k, t.per, t.phase)
                    of.write(string + "\n")
            else:
                for i, t in enumerate(self.dihedral_types, 1):
                    tags = self._get_tags(t, self.dihedrals)
                    if len(tags) > 20: tags = tags[:20]
                    of.write("%d charmm %f %d %d 0.0 #%s\n" % (i, t.phi_k, t.per, int(t.phase), tags))
            of.write("\n")

        # write atoms
        # avoid zero-charge-system error using ewald
        flag = True
        for a in self.atoms:
            if a.charge != 0.0:
                flag = False
                break
        if flag:
            self.atoms[0].charge = 0.00000001
            if len(self.atoms) > 1:
                self.atoms[1].charge = -0.00000001

        of.write("Atoms\n")
        of.write("\n")
        ks = list(self.atomtypes_with_resname.keys())
        for i, (a, r) in enumerate(zip(self.atoms, self.coordinates), 1):
            name = a.residue.name + a.type
            tid = ks.index(name) + 1
            imol = a.residue.number + 1
            of.write("%6d %6d %6d %13.8f %11.7f %11.7f %11.7f #%s:%s\n" % (i, imol, tid, a.charge, *r, a.residue.name, a.type))
        of.write("\n")
        of.write("Velocities\n")
        of.write("\n")
        for i in range(len(self.atoms)):
            of.write("%6d %11.7f %11.7f %11.7f\n" % (i + 1, 0.0, 0.0, 0.0))
        of.write("\n")

        self._write_dat_connects(of)

    def _write_molecule(self, of, parent=None):
        """Write LAMMPS molecule files"""

        tof = StringIO()
        tof.write("\n")
        tof.write("Coords\n")
        tof.write("\n")
        natoms = 0
        for a in self.each_atoms_only_unique_residue():
            r = self.coordinates[a.idx]
            tof.write("%6d %11.7f %11.7f %11.7f\n" % (natoms + 1, *r))
            natoms += 1

        tof.write("\n")
        tof.write("Types\n")
        tof.write("\n")
        i = 1
        if parent:
            ats = [k for k, _t in parent.atomtypes_with_resname.items()]
            for a, ut in self.each_atoms_only_unique_residue(with_unique_type=True):
                tid = ats.index(ut) + 1
                tof.write("%6d %6d #%s\n" % (i, tid, a.type))
                i += 1
        else:
            ats = [k for k in self.parameterset.atom_types]
            for a in self.each_atoms_only_unique_residue():
                tid = ats.index(a.type) + 1
                tof.write("%6d %6d#%s\n" % (i, tid, a.type))
                i += 1
        tof.write("\n")
        tof.write("Charges\n")
        tof.write("\n")
        i = 1
        for a in self.each_atoms_only_unique_residue():
            tof.write("%6d %11.7f\n" % (i, a.charge))
            i += 1
        tof.write("\n")
        tof.write("Molecules\n")
        tof.write("\n")
        i = 1
        for a in self.each_atoms_only_unique_residue():
            rid = self.residues.index(a.residue) + 1
            tof.write("%6d %6d\n" % (i, rid))
            i += 1
        tof.write("\n")

        if parent is None:
            master_props = None
        else:
            master_props = [parent.bonds, parent.angles, parent.dihedrals]
        nbonds, nangles, ndiheds = self._write_dat_connects(tof, only_unique_residue=True, master_props=master_props)
        string = tof.getvalue()
        if len(self.title) > 0:
            of.write("#smiles: {:s}\n".format(self.title))
        else:
            of.write("#generated by xtalmol\n")
        of.write("%d atoms\n" % (natoms))
        if len(self.bonds) >= 0:
            of.write("%d bonds\n" % (nbonds))
        of.write("%d angles\n" % (nangles))
        of.write("%d dihedrals\n" % (ndiheds))
        of.write("%d impropers\n" % (0))
        of.write(string)

    @staticmethod
    def _get_tags(ttype, target):

        tags = {}
        resname = None
        for prop in target:
            tmp = []
            if prop.type == ttype:
                resname = prop.atom1.residue.name
                assert resname == prop.atom2.residue.name
                tmp += [prop.atom1.type]
                tmp += [prop.atom2.type]
                if hasattr(prop, "atom3"):
                    assert resname == prop.atom3.residue.name
                    tmp += [prop.atom3.type]
                if hasattr(prop, "atom4"):
                    assert resname == prop.atom4.residue.name
                    tmp += [prop.atom4.type]
                tag = "-".join(tmp)
                if resname not in tags:
                    tags[resname] = [tag]
                elif tag not in tags[resname]:
                    tags[resname] += [tag]

        ret = []
        for resname, tag in tags.items():
            ret.append(resname + "(" + ",".join(tag) + ")")
        return ",".join(ret)

    def _write_dat_connects(self, of, only_unique_residue=False, master_props=None):

        if only_unique_residue:
            resorgs, _resname = self.get_unique_residue()
            noskip = False
        else:
            noskip = True

        if master_props:
            master_bonds, master_angles, master_dihedrals = master_props

        def check_unique_residue(residue):
            return noskip or residue.number in resorgs.keys()

        nbonds = 0
        nangles = 0
        ndiheds = 0
        if len(self.bonds) > 0:
            of.write("Bonds\n")
            of.write("\n")
            for b in self.bonds:
                if check_unique_residue(b.atom1.residue):
                    tid = b.type.idx + 1
                    if master_props:
                        for mb in master_bonds:
                            if b.type == mb.type and b.atom1.type == mb.atom1.type and b.atom2.type == mb.atom2.type:
                                tid = mb.type.idx + 1
                    b0 = b.atom1.idx + 1
                    b1 = b.atom2.idx + 1
                    b2 = b.atom1.residue.name
                    b3 = b.atom1.type
                    b4 = b.atom2.type
                    of.write("%6d %6d %6d %6d #%s:%s-%s\n" % (nbonds + 1, tid, b0, b1, b2, b3, b4))
                    nbonds += 1
            of.write("\n")
        if len(self.angles) > 0:
            of.write("Angles\n")
            of.write("\n")
            for a in self.angles:
                if check_unique_residue(a.atom1.residue):
                    tid = a.type.idx + 1
                    if master_props:
                        for ma in master_angles:
                            if a.type == ma.type and a.atom1.type == ma.atom1.type and a.atom2.type == ma.atom2.type and a.atom3.type == ma.atom3.type:
                                tid = ma.type.idx + 1
                    a0 = a.atom1.idx + 1
                    a1 = a.atom2.idx + 1
                    a2 = a.atom3.idx + 1
                    a3 = a.atom1.residue.name
                    a4 = a.atom1.type
                    a5 = a.atom2.type
                    a6 = a.atom3.type
                    of.write("%6d %6d %6d %6d %6d #%s:%s-%s-%s\n" % (nangles + 1, tid, a0, a1, a2, a3, a4, a5, a6))
                    nangles += 1
            of.write("\n")
        if len(self.dihedrals) > 0:
            of.write("Dihedrals\n")
            of.write("\n")
            for d in self.dihedrals:
                dtype = d.type
                if master_props:
                    for md in master_dihedrals:
                        if d.type == md.type and d.atom1.type == md.atom1.type and d.atom2.type == md.atom2.type and d.atom3.type == md.atom3.type and d.atom4.type == md.atom4.type:
                            dtype = md.type
                if type(dtype) == DihedralTypeList:
                    dtype = dtype[0]

                if check_unique_residue(d.atom1.residue):
                    if self._dihedralstyle == "fourier":
                        tid = ndiheds + 1
                    else:
                        tid = dtype.idx + 1
                    d0 = d.atom1.idx + 1
                    d1 = d.atom2.idx + 1
                    d2 = d.atom3.idx + 1
                    d3 = d.atom4.idx + 1
                    d4 = d.atom1.residue.name
                    d5 = d.atom1.type
                    d6 = d.atom2.type
                    d7 = d.atom3.type
                    d8 = d.atom4.type
                    of.write(
                        "%6d %6d %6d %6d %6d %6d #%s:%s-%s-%s-%s\n" % (ndiheds + 1, tid, d0, d1, d2, d3, d4, d5, d6, d7, d8)
                    )
                    ndiheds += 1
        return nbonds, nangles, ndiheds

    def write_lammps(self, fin="lmp.in", fdat="lmp.dat", orthogonality=False, padding=[0, 0, 0]):
        if not hasattr(self, 'pbc'):
            self.set_pbc()

        with open(fin, "w") as of:
            self._write_input(of, fdat)
        with open(fdat, "w") as of:
            self._write_data(of, orthogonality, padding)

    def _get_create_box_command(self):
        ns = [
            len(self.atomtypes_with_resname),
            len(self.bond_types),
            len(self.angle_types),
            len(self.dihedral_types),
        ]
        create_box_command = "create_box {} cell bond/types {} angle/types {} dihedral/types {}".format(*ns)
        create_box_command += " extra/bond/per/atom 6"
        create_box_command += " extra/angle/per/atom 12"
        create_box_command += " extra/dihedral/per/atom 24"
        create_box_command += " extra/special/per/atom 24"
        return create_box_command

    def _get_coeff_commands(self):
        of = StringIO()
        for i, (_k, t) in enumerate(self.atomtypes_with_resname.items(), 1):
            of.write("mass %d %11.7f #%s\n" % (i, t.mass, t.name))
        for i, (_k, t) in enumerate(self.atomtypes_with_resname.items(), 1):
            fact = 1.0
            line = "pair_coeff {0:d} {0:d} {1:11.7f} {2:11.7f}\n".format(i, fact * t.epsilon, t.sigma)
            of.write(line)
        for i, t in enumerate(self.bond_types, 1):
            line = "bond_coeff {0:d} harmonic {1:11.7f} {2:11.7f}\n".format(i, t.k, t.req)
            of.write(line)
        for i, t in enumerate(self.angle_types, 1):
            line = "angle_coeff {0:d} harmonic {1:11.7f} {2:11.7f}\n".format(i, t.k, t.theteq)
            of.write(line)
        for i, t in enumerate(self.dihedral_types, 1):
            line = "dihedral_coeff {0:d} charmm {1:11.7f} {2:d} {3:d} 0.0\n".format(i, t.phi_k, t.per, int(t.phase))
            of.write(line)
        return of.getvalue().split("\n")

    def _get_molecules(self):
        ret = []
        for (struc, x) in self.split():
            resname = struc.residues[0].name
            ret.append([struc.get_str_with_writer(struc._write_molecule, parent=self), resname, len(x)])
        return ret

    def get_lammps_info(self):
        molinfo = {}
        molinfo["lammps_molecules"] = self._get_molecules()
        molinfo["create_box_command"] = self._get_create_box_command()
        molinfo["coeff_commands"] = self._get_coeff_commands()
        molinfo["element_list"] = self.get_element_list()
        mesh = " ".join([str(x) for x in self.fftgrid])
        molinfo["style_commands"] = [
            self.pair_ljcoul,
            "pair_modify mix arithmetic shift no tail yes",
            "bond_style hybrid harmonic",
            "angle_style hybrid harmonic",
            f"dihedral_style hybrid {self._dihedralstyle}",
            "special_bonds amber lj 0.0 0.0 0.5 coul 0.0 0.0 0.83333 angle yes dihedral no",
            f"neighbor {self.cutoff_skin} multi",
            f"kspace_style pppm {self.ewald_error_tolerance}",
            f"kspace_modify gewald {self.gewald} mesh {mesh} order 6",
            "neigh_modify delay 0 every 1 check yes",
        ]
        return molinfo

    def to_ase(self, *args, **kwargs):
        ase = super().to_ase(*args, **kwargs)
        ase.info["lammps"] = self.get_lammps_info()
        return ase

    def set_pbc(self, pbc=[True, True, True]):
        self.pbc = pbc

    def get_element_list(self):
        from parmed.periodic_table import Element

        at = [at.atomic_number for _st, at in self.atomtypes_with_resname.items()]
        return [Element[i] for i in at]


class LAMMPSStructureFourier(LAMMPSStructure):

    _dihedralstyle = "fourier"

    def write_lammps(self, *args, **kwargs):
        self.join_dihedrals()
        super().write_lammps(*args, **kwargs)

